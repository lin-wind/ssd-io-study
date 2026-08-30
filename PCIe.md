### PCIe


BDF  Bus 8位 Device 5位 Function 3位
00:15.0 -> 00000000:10101.000 二进制

PCIe有4种空间: Configuration空间 Memory空间 IO空间 message空间


| 事务空间 (Space) | 事务类型 (TLP Type) | 发送属性 | 对应的响应包 (Completion) |
| :--- | :--- | :--- | :--- |
| **Memory** | 内存读 (MRd) | **Non-Posted** | CplD |
| | 内存写 (MWr) | **Posted** | 无  |
| | 带锁内存读 (MRdLk) | **Non-Posted** | CplLkD / CplLk |
| **Configuration** | 配置读 0 / 1 (CfgRd0/1) | **Non-Posted** | CplD |
| | 配置写 0 / 1 (CfgWr0/1) | **Non-Posted** | Cpl |
| **I/O** | I/O 读 (IORd) | **Non-Posted** | CplD |
| | I/O 写 (IOWr) | **Non-Posted** | Cpl |
| **Message** | 消息请求 (Msg / MsgD) | **Posted** | 无 |
| **Atomic** | 原子操作 (AtomicOp) | **Non-Posted** | CplD |

(Complete with Data) TLP


```
执行write(sq_tail) 
阶段一：Host 更新 SQ Tail Doorbell (MMIO Write - Posted 事务)      
PCIe 链路 (Host / Root Complex)                        PCIe 链路 (SSD)                  
    │─────── MWr TLP (数据: sq_tail) ─────────────────────>│ (物理接收)        
    │<────── Ack DLLP (确认 MWr 报文接收无误) ─────────────│ (电路自动回复) 

阶段二：SSD 主动 DMA 拉取 64B 命令 (Command Fetch - Non-Posted 事务)
    │<───── MRd TLP (请求 64 字节 SQE + SQ 物理地址) ───────│ (SSD 发起 DMA 读) 
    │───────── Ack DLLP (确认 MRd 报文接收无误) ───────────>│                   
 (从 Host DRAM 读出 64B 命令)                                                                  
    │──── CplD TLP (带 64B 命令数据: Opcode/CID/PRP) ─────>│ (完成报文下灌)    
    │<────── Ack DLLP (确认 CplD 报文接收无误) ─────────────│                   
 
阶段三：数据双向 DMA 搬运
(写操作 NVMe Write)
    │<─────────────── MRd TLP (请求数据) ──────────────────│ (SSD 沿 PRP 抓数据)
    │──────── Ack DLLP (确认 MRd 报文接收无误) ───────────>│                   
 (从 Host DRAM 读取用户数据)                                                                   
    │────────────── CplD TLP (数据) ──────────────────────>│ 
    │<──────── Ack DLLP (确认 CplD 报文接收无误) ───────────│                   
                                                                                           
(读操作 NVMe Read)
    │<─────────────── MWr TLP (数据 ) ─────────────────────│
    │────── Ack DLLP (确认 MWr 报文接收无误) ──────────────>│


阶段四：写回 16B CQE 结果 与 发射 MSI-X 硬件中断
    │             ─── 步骤 1：SSD DMA 写回 CQE ───          │
    │<──── MWr TLP (16B CQE 数据: Status/CID/Phase Tag) ───│ (写入 Host CQ 槽位)
    │─────── Ack DLLP (确认 MWr 报文接收无误) ─────────────>│
 (16B 写入 Host DRAM CQ)                                     
    │                                                      │
    │             ─── 步骤 2：SSD 发射 MSI-X 中断 ───       │
    │<───── MWr TLP (目标: 0xFEE00000 APIC, 载荷: 向量58) ──│ (发射中断报文)
    │─────── Ack DLLP (确认 MWr 报文接收无误) ──────────────>│

阶段五：Host 更新 CQ Head Doorbell (MMIO Write - Posted 事务)
Host / Root Complex                                       SSD
    │─────── MWr TLP (更新 cq_head) ─────────────────────>│ (通知 SSD 槽位已释放)
    │<────── Ack DLLP ────────────────────────────────────│

```




#### PCIe 配置空间
```
每个PCIe function 有4KB配置空间
┌─────────────────────────────────┐ 
│ 0x000 - 0x03F (共 64 字节)       │ ◄─── （Type 0 / 1 Header）
│ 标准 PCI 配置头 (Compatible)     │      存放 Device ID、Vendor ID、BAR0 等基础寄存器
├─────────────────────────────────┤ 
│ 0x040 - 0x0FF (共 192 字节)      │ ◄─── 传统 PCI 能力结构体区 (Capabilities)
│ PCI 传统能力链表区              │      用链表连着：MSI 中断、电源管理 (PM) 
│ (包含 CAP_EXP 链路调速寄存器)     │      以及【PCI Express 能力结构体】
▼═════════════════════════════════▼ ◄─── [256 字节分界线] 传统老 PCI 只能访问到这里
▲═════════════════════════════════▲
│ 0x100 - 0xFFF (共 3840 字节)     │ ◄─── PCIe 扩展配置空间 (Extended Configuration Space)
│ PCIe 扩展能力结构体区           │      也是用链表连接，全都是现代 PCIe 特有的高级功能
│ (包含 AER 高级错误报告寄存器)    │      例如：AER 错误报告、Lane Margining、虚拟通道 (VC) 等
└─────────────────────────────────┘
```

**nvme 属于Header Type 0**

![1787906567283](image/PCIe/1787906567283.jpg)



```

$ sudo lspci -s 03:00.0 -xxx 查看前256Bytes (-xxxx就是查看4KB)
 
03:00.0 Non-Volatile memory controller: VMware NVMe SSD Controller
00: ad 15 f0 07 07 04 10 00 00 02 08 01 00 00 00 00
10: 04 c0 4f fd 00 00 00 00 01 40 00 00 00 00 00 00
20: 00 00 00 00 00 00 00 00 00 00 00 00 ad 15 f0 07
30: 00 00 00 00 40 00 00 00 00 00 00 00 0a 01 00 00
40: 01 50 03 c8 00 00 00 00 00 00 00 00 00 00 00 00
50: 05 70 80 00 00 00 00 00 00 00 00 00 00 00 00 00
60: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
70: 11 80 0f 80 00 20 00 00 00 30 00 00 00 00 00 00
80: 10 00 02 00 00 00 00 00 00 00 00 00 02 06 00 00
90: 00 00 02 02 00 00 00 00 00 00 00 00 00 00 00 00
a0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
b0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
c0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
d0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
e0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
f0: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

Vendor ID: 15ad
Device ID: 07f0
BAR0: fd4fc004 
BAR（Memory BAR）的低 4 位（Bit 0 到 Bit 3）含义：
Bit 0 (值为 0)：说明这是一个内存映射（MMIO）空间（如果是 1 则代表 I/O 端口空间）
Bit 1 - Bit 2 (值为 10，即十进制的 2)：
00 = 32 位地址空间
10 = 64 位地址空间（64-bit base）
Bit 3 (值为 0)：表示该空间不可预取（Non-prefetchable）
二进制的 0100 对应十六进制的 4

BAR1: 00000000
基地址BAR0+BAR1(64位) : 00000000fd4fc000
```





```
Capabilities Pointer: 40  指向地址

 字节地址：    0x40                 0x41
             ┌────────────────────┬────────────────────┐
 寄存器定义： │   Capability ID    │    Next Pointer    │
             │   (功能身份证)      │   (下一个功能指针)  │
             └────────────────────┴────────────────────┘
 长度：       1 字节 (8 bits)       1 字节 (8 bits)

34:40
40:01 50   01 -> PCI Power Manage
50:05 70   05 -> MSI
70:11 80   11 -> MSI-X
80:10 00结束  10 -> PCI Express Capability
```