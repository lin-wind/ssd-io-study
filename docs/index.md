# Linux 存储 I/O 栈梳理

> **Linux内核版本6.17**
> 从 **用户态应用 I/O**、**Linux VFS / 文件系统**、**通用块层（blk-mq）**、**NVMe 内核驱动**、**PCIe 总线协议** 到 **SSD 固件与 NAND 介质** 的存储 I/O 链路

---

## 1. 存储 I/O 路径架构

Linux 存储 I/O 栈横跨用户空间、内核空间和硬件总线设备，整体可分为以下三条核心路径：
```
┌──────────────────────────────────────────────────────────────────────┐
│                        用户空间 (User Space)                         │
│  [ 应用程序 App / DB ] ──> [ I/O 库 (glibc POSIX / libaio / liburing)]│
└──────────────────────────────────┬───────────────────────────────────┘
                                   │ 系统调用 (Syscall)
┌──────────────────────────────────▼───────────────────────────────────┐
│                        内核空间 (Kernel Space)                       │
│                                                                      │
│  [ 虚拟文件系统 VFS ] ─┬─(Direct/Buffered I/O)─> [ 本地文件系统      │
│                        │                         (EXT4/XFS) ]        │
│                        └─(Raw 裸盘 I/O)───────────────┐              │
│                                                       │              │
│  ┌── 通用块层 (Block Layer) ──────────────────────────▼───────────┐  │
│  │ [ bio 组装与切分 ] ──> [ 多队列机制 (blk-mq) ] <──> [ I/O 调度器]│  │
│  └───────────────────────────────┬────────────────────────────────┘  │
│                                  │ nvme_queue_rq()                   │
│  ┌── 驱动与总线层 ───────────────▼────────────────────────────────┐  │
│  │ [ NVMe Host 驱动 (nvme.ko) ] ──> [ Linux PCIe 总线子系统       │  │
│  │                                  (pci_driver) ]                │  │
│  └───────────────────────────────┬────────────────────────────────┘  │
└──────────────────────────────────┼───────────────────────────────────┘
                                   │ PCIe MMIO (敲门铃) / DMA 物理映射
┌──────────────────────────────────▼───────────────────────────────────┐
│                      硬件与外设 (Hardware Layer)                     │
│                                                                      │
│  [ Root Complex / Host DRAM ] <═(PCIe 差分链路 Gen3/4/5)═> [NVMe主控]│
│                                                                 │    │
│                                  [ NAND Flash 颗粒 ] <─[ FTL 固件 ]  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. 存储路径解析

### 2.1 主机 I/O 路径 
从用户发起 I/O 请求到内核块层分发：

$$\text{Application} \rightarrow \text{VFS} \rightarrow \text{FileSystem} \rightarrow \text{Block Layer (bio)} \rightarrow \text{blk-mq (request/hctx)}$$

* **系统调用层**：`read()` / `write()`、`libaio` (`io_submit`)、`io_uring` (`io_uring_enter`)、`ioctl`
* **文件系统与缓存**：Direct I/O 绕过缓存直接构建 `struct bio`
* **多队列块层（blk-mq）**：完成 bio 切分、合并（Merge）、调度排队并挂入硬件分发队列（`hctx`）

### 2.2 协议与驱动路径 
从块层请求转换为 NVMe 命令并交由硬件执行：
$$\text{blk-mq ops} \rightarrow \text{NVMe Host Driver} \rightarrow \text{PCIe MMIO (Doorbell)} \rightarrow \text{PCIe DMA}$$

* **命令构造**：驱动将 `request` 转换为 64 字节 NVMe SQE 命令，构建 PRP/SGL DMA 散列表
* **硬件触发**：通过 MMIO 写入 SSD 控制器的 SQ Tail Doorbell 门铃寄存器
* **数据搬运**：SSD 控制器作为 PCIe Bus Master 发起 DMA 读写 Host 物理内存
* **完成与中断**：SSD 写入 CQE 并向主机发送 MSI-X 中断，触发驱动中断处理函数 `nvme_irq()` 完成回收

### 2.3 设备内部路径 
SSD 控制器在介质层上的执行过程：
$$\text{NVMe前端接口} \rightarrow \text{固件(FTL)} \rightarrow \text{闪存控制器(ECC/FMC)} \rightarrow \text{NAND Flash}$$

* **FTL 映射**：LBA 到 PBA 的转换查找
* **介质控制**：通过 ONFI 或 Toggle  协议对特定 Channel / LUN / Block / Page 下发读、写、擦除操作
* **后台管理**：Garbage Collection 、Wear Leveling 、Bad Block Management

---

## 3. 项目文档索引

各文档定位与涵盖内容如下：

| 模块 | 对应文档 | 层级 | 
| :--- | :--- | :--- | 
| **01. 通用块层** | [Block Layer.md](./src/Block%20Layer.md) | OS 内核 | 
| **02. NVMe 协议** | [NVMe.md](./src/NVMe.md) | 协议 | 
| **03. Linux NVMe 系统** | [NVMe Driver.md](./src/NVMe%20Driver.md) | 驱动 | 
| **04. PCIe 协议** | [PCIe.md](./src/PCIe.md) | 总线 | 
| **05. Linux PCIe 系统** | [PCIe bus.md](./src/PCIe%20bus.md) | 总线驱动 | 
| **06. 用户态高性能 I/O** | [spdk.md](./src/spdk.md) | 用户态框架 | 
| **07. 基准测试与压测** | [fio.md](./src/fio.md) | 性能评测 | 



```{toctree}
:maxdepth: 2
:caption: 目录导航

src/Block Layer
src/NVMe Driver
src/NVMe
src/PCIe
src/PCIe bus
src/spdk
src/fio
```