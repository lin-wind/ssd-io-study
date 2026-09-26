# NVMe 协议

## 1. NVMe 寄存器与 BAR0 MMIO 内存布局

NVMe 寄存器存在于**PCIe BAR0 映射的内存空间 MMIO**中
将外设寄存器映射到物理内存地址段的技术，就叫做 MMIO（Memory-Mapped I/O）

### 1.1 BAR0 物理地址空间结构布局
```
PCIe BAR0 物理地址空间 (基地址 = dev->bar):
┌─────────────────────────────────────────────────────────────┐
│ 偏移 0x0000 ~ 0x0FFF (前 4096 字节): 控制器寄存器区           │
│  - 0x0000: CAP (能力寄存器)  8B                             │
│  - 0x0014: CC  (控制器配置使能) 4B                           │
│  - 0x001C: CSTS (控制器状态就绪) 4B                          │
│  - 0x0024: AQA (Admin 队列属性)  4B                          │
│  - 0x0028: ASQ  (Admin 队列基地址) 8B                        |
|  - 0x0030: ACQ  (Admin 队列基地址) 8B                        │
├─────────────────────────────────────────────────────────────┤ <--- NVME_REG_DBS (偏移 0x1000 / 4096 字节处)
│ 偏移 0x1000 往后: Doorbell 门铃寄存器阵列 (dev->dbs)          │
│  - 0x1000 + 0: SQ0 Tail Doorbell (Admin 队列写门铃)  4B      │
│  - 0x1000 + 4: CQ0 Head Doorbell (Admin 队列写门铃)  4B      │
│  - 0x1000 + 8: SQ1 Tail Doorbell (IO 队列 1 写门铃)  4B      │
│  - 0x1000 + C: CQ1 Head Doorbell (IO 队列 1 写门铃)  4B      │
│  - ... 后续所有 IO 队列的门铃  (按 DSTRD 步长依次递增)         │
└─────────────────────────────────────────────────────────────┘
```


### 1.2 物理地址读取

1. **读取设备 BAR0 地址**：
```bash
$ sudo cat /proc/iomem | grep -E "nvme|RAM"  
00001000-00091bff : System RAM
00100000-bfecffff : System RAM
bff00000-bfffffff : System RAM
      fd3fc000-fd3fffff : nvme
      fd4fc000-fd4fffff : nvme
100000000-43fffffff : System RAM

# 找到 NVMe 设备的 BDF
$ lspci | grep -i non 
03:00.0 Non-Volatile memory controller: VMware NVMe SSD Controller
0b:00.0 Non-Volatile memory controller: VMware NVMe SSD Controller

# 查看对应 BAR0 物理地址
$ lspci -s 03:00.0 -vv | grep Region 
	Region 0: Memory at fd4fc000 (64-bit, non-prefetchable) [size=16K]
	Region 2: I/O ports at 4000 [size=8]

# 查看对应 BAR0 物理地址
$ lspci -s 0b:00.0 -vv | grep Region  
	Region 0: Memory at fd3fc000 (64-bit, non-prefetchable) [size=16K]
	Region 2: I/O ports at 5000 [size=8]
```

2. **读取CC 寄存器**：

$$
Address_{CC} = Base\_Address_{BAR0} + 0x14
$$

```bash
# sudo devmem2 [物理地址] [数据宽度] [写入值]
# (b,h,w,l 或 q)分别表示 byte,half-word,word,long 表示 1, 2, 4, 8 Bytes

$ sudo devmem2 0xfd4fc014 w  # 读取CC寄存器对应的值
/dev/mem opened.
Memory mapped at address 0x70c5b4bc0000.
Value at address 0xFD4FC014 (0x70c5b4bc0014): 0x460001
```

- **数值解析 (`0x00460001`)**：
  - **Bit 0 (`1`)**：`EN = 1`（Controller Enable）
  - **Bit 6:4 (`110`b)**：`CSS = 0`（NVM Command Set，使用标准 NVM 命令集）
  - **Bit 19:16 (`0110`b)**：`IOCQES = 4`（I/O CQE 宽度 $2^4 = 16$ 字节）
  - **Bit 23:20 (`0100`b)**：`IOSQES = 6`（I/O SQE 宽度 $2^6 = 64$ 字节）


## 2. NVMe Doorbell 门铃系统

### 2.1 Doorbell 寄存器 4 字节位域结构

```
SQ / CQ Doorbell 4字节
+---------------------------------+---------------------------------+
|     Bit 31 ~ Bit 16 (高2字节)    |    Bit 15 ~ Bit 0 (低2字节)      |
+---------------------------------+---------------------------------+
|       Reserved (硬件保留位)       |      SQ Tail Pointer (尾指针)   |
|         永远返回全 0             |        当前队列的任务位置         |
---------------------------------------------------------------------
|       Reserved (硬件保留位)       |      CQ Head Pointer (头指针)   |
|         永远返回全 0             |        当前队列已处理的任务位置    |
+---------------------------------+---------------------------------+
```
> [!NOTE]
> 门铃步长由 CAP 寄存器中的 `DSTRD` 字段决定：$\text{Stride} = 2^{(2 + \text{DSTRD})}$ 字节
> 当 $\text{DSTRD}=0$ 时，步长为 4 字节；SQ Tail 与 CQ Head 门铃依次相邻排布
> 当 $\text{DSTRD}=1$ 时，步长为 8 字节；每个门铃内部强制插入 4 字节空白填充空间

### 2.2 读取 Admin SQ / CQ 门铃

```bash
$ sudo devmem2 0xfd4fd000 w  # admin sq队列

/dev/mem opened.
Memory mapped at address 0x7effc6dd7000.
Value at address 0xFD4FD000 (0x7effc6dd7000): 0x9

$ sudo devmem2 0xfd4fd004 w  # admin cq队列

/dev/mem opened.       # 通过/dev/mem然后mmap访问的物理地址空间
Memory mapped at address 0x77d281858000.
Value at address 0xFD4FD004 (0x77d281858004): 0x8
```







## 3. DMA 内存描述机制：PRP 与 SGL

### 3.1 PRP 机制与 SGL
- PRP描述符8字节，以 4KB 物理页为基本粒度，除首尾页允许页内偏移外，中间所有页必须 4KB 对齐且固定为 4KB 整页
- SGL描述符16字节，64位地址 + 32位长度 + 8位类型，支持任意物理起始地址、任意字节长度（从 1 字节到 4GB 均可）

**PRP1 和PRP2** 
| 数据实际占用的物理页数 | 典型数据量示例 | `PRP1` 存什么？ | `PRP2` 存什么？ | 是否需要 PRP List 链表？ |
| :--- | :--- | :--- | :--- | :--- |
| **1 个物理页** | 512B / 4KB（对齐） | 物理页 1 首地址（允许页内偏移） | **置 0（空）** |  不需要 |
| **2 个物理页** | 8KB（对齐）/ 跨页 4KB | 物理页 1 首地址（允许页内偏移） | **物理页 2 首地址**（必须 4KB 对齐） |  不需要 |
| **$3 \sim 513$ 个物理页** | 12KB ~ 2MB | 物理页 1 首地址（允许页内偏移） | **第 1 个 PRP List 链表页物理地址** |  需要（单级 4KB 链表页） |
| **$> 513$ 个物理页** | 4MB ~ 32MB | 物理页 1 首地址（允许页内偏移） | **第 1 个 PRP List 链表页物理地址** |  需要（多级链表接力跳转） |


## 4. NVMe 核心命令报文格式 (SQE 与 CQE)

### 4.1 SQE(64字节)


### 4.2 CQE(16字节)


