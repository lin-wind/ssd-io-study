# Linux NVMe Driver

## 1. NVMe 驱动

### 1.1 内核模块编译
驱动基于6.17.0-41-generic 环境 24.04.1-Ubuntu

```bash
$ sudo apt update 

$ apt-get source linux-hwe-6.17
# 提示
Reading package lists... Done
E: You must put some 'deb-src' URIs in your sources.list

# 修改配置文件
$ sudo sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources

$ sudo apt update 
$ apt-get source linux-hwe-6.17
# 查看/debian/changelog或者是下载的.dsc发现为Main version: 6.17.0-41.41~24.04.1
# 升级本地ubuntu 内核到-41 和 安装对应开发头文件包
$ sudo apt install linux-image-6.17.0-41-generic linux-headers-6.17.0-41-generic
$ sudo reboot

# 查看相关依赖是否安装
$ dpkg -l build-essential libncurses-dev bison flex libssl-dev libelf-dev libdw-dev dwarves gawk
# 安装对应包
$ sudo apt install -y build-essential libncurses-dev bison flex libssl-dev libelf-dev libdw-dev dwarves gawk

# 在对应根目录下进行模块编译配置
# 方式一: 本地目录编译
$ make olddefconfig      # 根据旧的.config生成.config文件
$ make modules_prepare     # 准备模块化编译
$ make M=drivers/nvme/host modules   # 模块编译

# 方式二: 借用自带环境
$ make -C /lib/modules/6.17.0-41-generic/build M=$PWD/drivers/nvme/host modules

(内核编译 make menuconfig  make -j$(nproc) )
```

- 编译出对应nvme.ko nvme-fabrics.ko nvme-fc.ko nvme-core.ko等等文件


### 1.2 模块加载与卸载
```bash
# 临时卸载对应驱动(先卸载nvme再卸载它的依赖nvme_core)
# 系统不能在nvme盘上否则卸载崩溃
$ sudo rmmod nvme
$ sudo rmmod nvme_core

# 临时加载对应驱动(可附带参数)
$ sudo insmod nvme_core.ko
$ sudo insmod nvme.ko
$ sudo insmod nvme.ko poll_queues=2 io_queue_depth=512
$ lsmod | grep nvme

# 加载原先 `/lib/modules`的驱动
$ sudo modprobe nvme
```


### 1.3 模块调试与打印控制
```c
// 创建一个静态变量，默认设置为0
static bool my_debug_mode = false;
// 创造功能开关：将其注册为内核模块参数，类型为 bool，权限为 0644
module_param(my_debug_mode, bool, 0644);
// 编写说明书：让 modinfo 能够识别并打印这段解释
MODULE_PARM_DESC(my_debug_mode, "Enable my custom NVMe driver deep debug logging (default: false)");

// 可以通过实时修改或者驱动加载时修改参数，查看打印信息
// echo 1 | sudo tee /sys/module/nvme/parameters/my_debug_mode

// 打印信息
if (my_debug_mode) {
    dev_info(dev->dev, "MY_DEBUG: INFO!\n");
}
```


**日志等级**
```bash
$ cat /proc/sys/kernel/printk
4 4 1 7

# 控制台小于 4 打印
# 默认消息等级为 4
# 第一个数字最小为 1
# 出厂控制台等级为 7

# 0 emergency 1 alert 2 critical 3 error 4 warning 5 notice 6 info 7 debug
```



## 2. 驱动数据结构

### 2.1 `struct nvme_dev`

```c
struct nvme_dev {
    struct nvme_queue *queues;    // 硬件队列数组指针
	struct blk_mq_tag_set tagset;    // IO请求tag标签集
	struct blk_mq_tag_set admin_tagset;    // Admin管理命令tag标签集
	u32 __iomem *dbs;         // Doorbell寄存器起始内存地址
	struct device *dev;    // dev
	unsigned online_queues;   // 当前激活队列数
	unsigned io_queues[HCTX_MAX_TYPES];
	unsigned int num_vecs;    // 申请到的MSI-X中断向量数
	u32 q_depth;         // IO 队列深度
	u32 db_stride;        // 门铃步长
	void __iomem *bar;    // PCIe BAR0寄存器虚拟基地址
	unsigned long bar_mapped_size;  // BAR0映射物理内存大小
	u64 cmb_size;        // SSD 板载CMB内存大小
	bool cmb_use_sqes;   // 是否将SQ队列建立 CMB中
	u32 cmbsz;           // CMB大小
	u32 cmbloc;          // CMB位置寄存器(基地址+偏移量)
	struct nvme_ctrl ctrl;    // nvme ctrl
	u32 last_ps;      // 上次功耗状态
	bool hmb;                // HMB特性是否开启
	struct sg_table *hmb_sgt;   // HMB散列表
	/* shadow doorbell buffer support: 将 Doorbell 寄存器的 MMIO 写操作，转化为 Host DRAM 的本地内存写操作，减少PCIe MMIO开销*/
	__le32 *dbbuf_dbs;    // 影子门铃虚拟地址
	dma_addr_t dbbuf_dbs_dma_addr;  // 影子门铃DMA物理地址
	__le32 *dbbuf_eis;      // Event Index虚拟地址
	dma_addr_t dbbuf_eis_dma_addr;    // Event Index DMA物理地址

	u64 host_mem_size;          // 主机借给SSD内存大小
	unsigned int nr_write_queues;      // 独立写队列数量
	unsigned int nr_poll_queues;      // 开启IO polling队列数量
    [...]

};
```



### 2.2 `struct nvme_queue`

```c
struct nvme_queue {
    struct nvme_dev *dev;
	struct nvme_descriptor_pools descriptor_pools;
	spinlock_t sq_lock;   // SQ 队列自旋锁
	void *sq_cmds;       // SQ队列虚拟首地址(CPU读取，内存里)
	 /* only used for poll queues: */
	spinlock_t cq_poll_lock ____cacheline_aligned_in_smp;
	struct nvme_completion *cqes;   // CQ队列虚拟首地址
	dma_addr_t sq_dma_addr;     // SQ队列DMA首地址
	dma_addr_t cq_dma_addr;     // CQ队列DMA首地址
	u32 __iomem *q_db;   // Doorbell寄存器虚拟地址
	u32 q_depth;     // 队列深度
	u16 sq_tail;   // SQ 尾指针
	u16 last_sq_tail;  // 上一次敲门铃的SQ Tail值
	u16 cq_head;  // CQ 头指针
	u16 qid;      // 队列编号
	u8 cq_phase;  // CQ 相位位
	u8 sqes;
    unsigned long flags;
#define NVMEQ_ENABLED		0
#define NVMEQ_SQ_CMB		1
#define NVMEQ_DELETE_ERROR	2
#define NVMEQ_POLLED		3
	__le32 *dbbuf_sq_db;
	__le32 *dbbuf_cq_db;
	__le32 *dbbuf_sq_ei;
	__le32 *dbbuf_cq_ei;
	struct completion delete_done;
    [...]
};
```


### 2.3 `struct nvme_iod`

```c
struct nvme_iod {
    struct nvme_request req;
	struct nvme_command cmd;    // SQE cmd
	u8 flags;     // 标志位
	u8 nr_descriptors;    // 实际使用SGL/PRP List页数量  
	unsigned int total_len;     // 本次IO传输数据总字节数
	struct dma_iova_state dma_state;
	void *descriptors[NVME_MAX_NR_DESCRIPTORS];
	struct nvme_dma_vec *dma_vecs;
	unsigned int nr_dma_vecs;    // DMA散列向量数量 IO 在物理内存中的物理连续块数量
	dma_addr_t meta_dma;
	struct sg_table meta_sgt;
	struct nvme_sgl_desc *meta_descriptor;

};
```


### 2.4 `struct nvme_ctrl`

```c
struct nvme_ctrl {
	enum nvme_ctrl_state state;    // 控制器状态
	const struct nvme_ctrl_ops *ops;
	struct request_queue *admin_q;    // Admin管理队列指针
	struct work_struct reset_work;    // 异步重置任务
	u16 cntlid;    // 控制器id
	u32 ctrl_config;   // 控制器配置寄存器CC镜像
	u64 cap;     // Controller Capability
	u32 max_hw_sectors;   // 单次IO允许最大扇区数
	u32 max_segments;    // 单次IO允许最大散列物理段数
	u16 oncs;    // Optional NVMe Command Support
	u16 oacs;      // Optional Admin Command Support
    u32 max_namespaces;   // 支持的最大命名空间
	u8 vwc;        // Volatile Write Cache 易失性写缓存  bit0=1 表示SSD带DRAM缓存
	u32 vs;        // NVMe版本协议号
	u32 sgls;     // SGL支持能力 bit0=1 表示SSD支持SGL
	u8 npss;       // Number of Power States Support 支持的功耗状态数
	u8 apsta;       // APST 自适应电源状态特性属性
	u16 wctemp;       // 告警温度阈值
	u16 cctemp;       // 严重危险温度阈值
	u32 oaes;      // Optional Asynchronous Events Support
	u32 aen_result;   // AEN 事件结果
	u32 ctratt;     // 控制器属性
	unsigned int shutdown_timeout;   // 下电关机超时等待时间
	struct work_struct fw_act_work;   // 固件在线激活任务
	u64 ps_max_latency_us;     // 允许的最大休眠唤醒延迟
	bool apst_enabled;      // APST 自动节能是否已使能
	u32 hmpre;     // HMB最佳内存大小
	u32 hmmin;     // 支持SSD的最小 HMB 内存大小 
	struct nvme_fault_inject fault_inject;      // NVMe故障注入
    [...]

};
```






## 3. 驱动注册与操作

### 3.1 core.c

```c
/* 1. 字符设备操作集 (core.c: 服务于/dev/nvme0 支持 nvme-cli 工具的 ioctl 与 io_uring) */
static const struct file_operations nvme_dev_fops = {
	.owner		= THIS_MODULE,
	.open		= nvme_dev_open,
	.release	= nvme_dev_release,
	.unlocked_ioctl	= nvme_dev_ioctl,
	.compat_ioctl	= compat_ptr_ioctl,
	.uring_cmd	= nvme_dev_uring_cmd,
};

/*2. 命名空间字符设备操作集 (core.c: 服务于 /dev/ng0n1，提供绕过通用块层的纯粹直通通道，支持 io_uring 与ioctl) */
static const struct file_operations nvme_ns_chr_fops = {
	.owner		= THIS_MODULE,
	.open		= nvme_ns_chr_open,
	.release	= nvme_ns_chr_release,
	.unlocked_ioctl	= nvme_ns_chr_ioctl,
	.compat_ioctl	= compat_ptr_ioctl,
	.uring_cmd	= nvme_ns_chr_uring_cmd,
	.uring_cmd_iopoll = nvme_ns_chr_uring_cmd_iopoll,
};
```


### 3.2 pci.c

```c
[module_init] --> nvme_init()
-> pci_register_driver(&nvme_driver)
[module_exit] --> nvme_exit()
-> pci_unregister_driver(&nvme_driver)
```



```c
/* 2. PCIe 驱动注册 (pci.c: 系统总线枚举) */
static struct pci_driver nvme_driver = {
	.name		= "nvme",
	.id_table	= nvme_id_table,
	.probe		= nvme_probe,
	.remove		= nvme_remove,
	.shutdown	= nvme_shutdown,
	.driver		= {
		.probe_type	= PROBE_PREFER_ASYNCHRONOUS,
#ifdef CONFIG_PM_SLEEP
		.pm		= &nvme_dev_pm_ops,
#endif
	},
	.sriov_configure = pci_sriov_configure_simple,
	.err_handler	= &nvme_err_handler,
};

```


```c
/* 3. 多队列块层 (pci.c: 桥接通用块层) */
static const struct blk_mq_ops nvme_mq_admin_ops = {
	.queue_rq	= nvme_queue_rq,
	.complete	= nvme_pci_complete_rq,
	.init_hctx	= nvme_admin_init_hctx,
	.init_request	= nvme_pci_init_request,
	.timeout	= nvme_timeout,
};

static const struct blk_mq_ops nvme_mq_ops = {
	.queue_rq	= nvme_queue_rq,
	.queue_rqs	= nvme_queue_rqs,
	.complete	= nvme_pci_complete_rq,
	.commit_rqs	= nvme_commit_rqs,
	.init_hctx	= nvme_init_hctx,
	.init_request	= nvme_pci_init_request,
	.map_queues	= nvme_pci_map_queues,
	.timeout	= nvme_timeout,
	.poll		= nvme_poll,
};
```




```c
/* 4. 错误处理*/
static const struct pci_error_handlers nvme_err_handler = {
	.error_detected	= nvme_error_detected,    
	.slot_reset	= nvme_slot_reset,
	.resume		= nvme_error_resume,
	.reset_prepare	= nvme_reset_prepare,
	.reset_done	= nvme_reset_done,
};
```



```c
/* 5. 控制器状态*/
nvme_ctrl_state
- NVME_CTRL_NEW 0
- NVME_CTRL_LIVE
- NVME_CTRL_RESETTING
- NVME_CTRL_CONNECTING
- NVME_CTRL_DELETING
- NVME_CTRL_DELETING_NOIO
- NVME_CTRL_DEAD
```


### 3.3 驱动探测与初始化

```c
nvme_probe()
  │
  ├── nvme_pci_alloc_dev(pdev, id) [pci.c]
  │   ├── kzalloc_node()                      // 分配 struct nvme_dev 实例
  │   ├── INIT_WORK(&dev->ctrl.reset_work)    // 绑定 reset_work 
  |   ├── nvme_init_ctrl() [core.c]           // 初始化通用控制器基类
  |   ├── dma_set_mask_and_coherent()        // 设置 64位 DMA寻址 
  │   └── 设置 单次I/O 硬件边界              // max_hw_sectors=1MB, max_segments=256, max_integrity_segments=1
  │
  ├── nvme_add_ctrl(&dev->ctrl) [core.c]
  │   ├── dev_set_name()                     // 命名字符设备名称为 "nvme0" (基于 instance 编号)
  │   ├── cdev_init(&ctrl->cdev, &nvme_dev_fops)     // 绑定用户态操作接口 (支持 nvme-cli 的 ioctl 与 uring_cmd)
  │   ├── cdev_device_add()                  // 正式注册字符设备，生成 /dev/nvme0 与 sysfs 目录
  │   ├── dev_pm_qos_update...()             // 初始化 PM QoS 延迟容忍度 (服务于 APST 节能休眠)
  │   └── nvme_fault_inject_init()           // 初始化 debugfs 故障注入控制节点
  │   
  │
  ├── nvme_dev_map(dev) [pci.c]
  │   ├── pci_request_mem_regions()          // 向系统独占申请 PCIe BAR0 物理地址空间
  │   └── nvme_remap_bar()                   // 调用 ioremap() 映射 BAR0 物理空间到内核虚拟内存
  │       ├── dev->bar = ioremap(...)      // 控制器寄存器基地址 (用于后续读写 CAP/CC/CSTS)
  │       └── dev->dbs = dev->bar + NVME_REG_DBS (4096) // 定位 Doorbell 门铃起始虚拟地址 (SQ0 Tail Doorbell 偏移)
  │
  ├── nvme_pci_alloc_iod_mempool(dev) [pci.c]
  │   ├── mempool_create_node(dmavec)         // 创建 DMA 散列向量紧急内存池 (支持 256 个物理页，防 OOM 刷盘死锁)
  │   └── mempool_create_node(iod_meta)      // 创建端到端数据保护 (T10 DIF/PI) 元数据紧急内存池
  │
  ├── nvme_pci_enable(dev) [pci.c]
  │   ├── pci_enable_device_mem() & pci_set_master()     // 唤醒 PCIe 硬件物理层并使能 Bus Master 
  │   ├── lo_hi_readq(dev->bar + NVME_REG_CAP)     // 读取 CAP 寄存器 (获取 MQES 最大深度、DSTRD 门铃步长)
  │   ├── nvme_map_cmb()                     // 探测并映射 SSD 板载 CMB 内存
  │   └── nvme_pci_configure_admin_queue()   // 配置并硬件启动 Admin 队列
  │       ├── nvme_disable_ctrl()                // 写 CC.EN=0 关闭控制器
  │       ├── nvme_alloc_queue(0)                // 调用 dma_alloc_coherent 分配 SQ0/CQ0 物理 DMA 内存
  │       ├── 写入 AQA / ASQ / ACQ 寄存器        // 告诉 SSD 硬件 SQ0/CQ0 的 DMA 物理首地址
  │       ├── nvme_enable_ctrl()                 // 写入 CC.EN=1 并等待 CSTS.RDY==1 (主控就绪)
  │       ├── nvme_init_queue(0)                 // 初始化游标：cq_head=0, cq_phase=1, 定位 q_db 门铃
  │       ├── queue_request_irq()                // 绑定 0 号中断向量与 nvme_irq 中断处理函数
  │       └── set_bit(NVMEQ_ENABLED)             // 标记 Admin 队列状态为已启用 (online_queues++)
  │
  ├── nvme_alloc_admin_tag_set(dev) [core.c]
  │   ├── blk_mq_alloc_tag_set()             // 分配 Admin 标签池 (深度32，管理 0~31 号 Command ID/CID)
  │   └── blk_mq_alloc_queue()           // 创建 ctrl->admin_q 请求队列 (绑定 60秒 超时检测机制)
  │
  ├── nvme_change_ctrl_state(&dev->ctrl, NVME_CTRL_CONNECTING) [core.c]
  │   └── 【状态机】：从 NVME_CTRL_NEW  ──>  NVME_CTRL_CONNECTING (允许发 Admin 命令)
  │
  ├── nvme_init_ctrl_finish(&dev->ctrl) [core.c]
  │   ├── reg_read32(NVME_REG_VS)            // 读取 NVMe 版本号寄存器 (如 1.4 / 2.0)
  │   ├── nvme_init_identify()               // 下发 Identify Controller (0x06) 读取 4KB 身份信息
  │   │   └── nvme_identify_ctrl()         // 解析 SN、MN、FW版本、MDTS
  │   ├── 配置 (时间戳/APST/hwmon)        // 同步系统时间戳、配置节能休眠并注册 hwmon 温度监控
  │   └── nvme_start_keep_alive()            // 启动保活心跳定时器
  │
  ├── nvme_ctrl_meta_sgl_supported(&dev->ctrl)
  │   └── 检查控制器是否支持元数据 SGL 格式 (用于 T10 DIF/PI 端到端数据校验)
  │
  ├── nvme_dbbuf_dma_alloc(dev) [pci.c]
  │   └── 若主控支持 Shadow Doorbell，在主机内存中为影子门铃与 EventIdx 分配 DMA 内存
  │
  ├── nvme_setup_host_mem(dev) [pci.c]
  │   └── 若是 DRAM-less 盘且支持 HMB，按 hmpre/hmmin 借出 Host 内存并通知 SSD
  │
  ├── nvme_update_attrs(&dev->ctrl) [pci.c]
  │   └── 根据 Identify 读到的属性，动态刷新 sysfs 中的只读/读写节点
  │
  ├── nvme_setup_io_queues(dev) [pci.c]
  │   ├── nvme_set_queue_count()             // 协商 I/O 队列总数
  │   ├── nvme_remap_bar()                   // 重新映射 BAR0 完整空间 (覆盖所有 IO 队列的门铃)
  │   ├── nvme_setup_irqs()                  // 申请 N+1 个 MSI-X 中断向量并自动绑定 CPU 核心亲和性
  │   └── nvme_create_io_queues()            // 循环创建各核 SQ/CQ 队列:
  │       ├── 下发 Create I/O CQ (0x05)    // 告知 SSD 各 CQ 的 DMA 物理基地址与对应 MSI-X 中断号
  │       ├── 下发 Create I/O SQ (0x01)    // 告知 SSD 各 SQ 的 DMA 物理基地址并关联对应 CQ
  │       └── queue_request_irq()          // 绑定各队列 MSI-X 中断号与 nvme_irq 中断处理函数
  │
  ├── nvme_alloc_io_tag_set(&dev->ctrl, &dev->tagset, &nvme_mq_ops, ... ) [core.c]
  │   ├── blk_mq_alloc_tag_set()             // 初始化 I/O 标签池 (绑定 N 个硬件队列与 队列深度)
  │   └── 绑定核心业务 nvme_mq_ops     // .queue_rq(写盘发命令), .timeout(30秒超时检测)
  │
  ├── nvme_dbbuf_set(dev) [pci.c]
  │   └── 下发 Doorbell Buffer Config  SSD 注册影子门铃物理地址
  │
  ├── nvme_change_ctrl_state(&dev->ctrl, NVME_CTRL_LIVE) [core.c]
  │   └── 【状态机】：从 NVME_CTRL_CONNECTING  ──>  NVME_CTRL_LIVE (允许业务读写)
  │
  ├── pci_set_drvdata(pdev, dev)
  │   └── 把 struct nvme_dev 绑定到 pci_dev
  │
  ├── nvme_start_ctrl(&dev->ctrl) [core.c]
  │   ├── nvme_enable_aen()                  // 下发 AEN 异步事件请求
  │   └── nvme_queue_scan()                  // 将 scan_work 扫描任务推入异步工作队列 nvme_wq
  │                                          // 执行nvme_scan_work(),一系列过程之后注册/dev/nvme0n1和/dev/ng0n1
  |                                     
  ├── nvme_put_ctrl(&dev->ctrl) 
  │   └── 释放 probe 过程中持有的临时控制器引用计数 (平衡计数器)
  │
  └── flush_work(&dev->ctrl.scan_work) 
      └── 同步等待扫描任务完成，确保 nvme_probe() 返回时，/dev/nvme0n1 节点出现在系统
```


一次调用nvme_queue_rq()队列只写入一个SQE，最大传输数据(最小内存页大小 MPSMIN * 2^MDTS)(mpsmin一般为4KB也能大页内存2mb)

           

## 4. 数据下发路径

**NVMe处理命令步骤**
- 主机写命令到 SQ
- 主机写 SQ 的 DB，通知 SSD 取指
- SSD 收到通知后， 到 SQ 取指
- SSD 执行指令
- 指令执行完成， SSD 往 CQ中写指令执行结果
- SSD发中断通知主机指令完成
- 收到中断，主机处理 CQ，查看指令完成状态
- 主机处理完 CQ 中的指令执行结果，通过 DB 回复 SSD

### 4.1 单请求下发与批量下发 

```c
nvme_queue_rq()
  ├── nvme_prep_rq()        // 准备 command
  │   ├── nvme_setup_cmd() // 填充 64 字节 SQE
  │   │ 
  │   ├── nvme_map_data()       // 建立 DMA 映射
  │   ├── nvme_map_metadata()   // (可选) 元数据映射 
  │   └── nvme_start_request()  
  │       └── blk_mq_start_request()  // 启动超时计时器
  │
  ├── nvme_sq_copy_cmd()    // [第一步] 命令写入 host 内存 SQ 槽位
  └── nvme_write_sq_db()
        更新 nvmeq->sq_tail
        writel(nvmeq->sq_tail, nvmeq->q_db)  // [第二步] writel 敲响 SQ DB

nvme_queue_rqs()
  │     批量提取 req
  │      // 如果 req 的 nvme queue与上个不一样 ，先提交完 nvme_submit_cmds()
  ├── nvme_prep_rq_batch()   
  │   └── nvme_prep_rq() 
  ├── rq_list_add_tail()    //成功的 req 加入 submit_list，失败的加入 requeue_list
  │
  │
  └── nvme_submit_cmds()   // 统一提交 submit_list
      ├── nvme_sq_copy_cmd()    // 命令写入 host 内存 SQ 槽位
      └── nvme_write_sq_db()
            更新 nvmeq->sq_tail
            writel(nvmeq->sq_tail, nvmeq->q_db)  // [第二步] writel 敲响 SQ DB
```




### 4.2 写入 SQ 环形缓冲区与门铃更新流程

```c
# 把64字节的NVMe命令复制到内存中由环形缓冲区构成的SQ中
nvme_sq_copy_cmd(nvmeq, &iod->cmd);
{
    # nvmeq->sq_cmds:队列在主内存中的起始首地址
    # nvmeq->sq_tail:当前的格子编号
    # nvmeq->sqes:sqe大小的二进制对数为6  (2^6 =64)
    memcpy(nvmeq->sq_cmds + (nvmeq->sq_tail << nvmeq->sqes),
		absolute_pointer(cmd), sizeof(*cmd));

    # 尾指针+1，判断是否达到队列深度
	if (++nvmeq->sq_tail == nvmeq->q_depth)
		nvmeq->sq_tail = 0;
}

# 将计算的尾指针写入到SSD控制器的PCIe寄存器中，敲门铃
nvme_write_sq_db(nvmeq, bd->last);
{
    # 如果blk-mq本次下发的不是最后一个请求，即bd->last为假且没有要撞上一次敲响门铃的位置，就一直写
    if (!write_sq) {
		u16 next_tail = nvmeq->sq_tail + 1;

		if (next_tail == nvmeq->q_depth)
			next_tail = 0;
		if (next_tail != nvmeq->last_sq_tail)
			return;
	}
    # writel敲响门铃
	if (nvme_dbbuf_update_and_check_event(nvmeq->sq_tail,
			nvmeq->dbbuf_sq_db, nvmeq->dbbuf_sq_ei))
		writel(nvmeq->sq_tail, nvmeq->q_db);
	nvmeq->last_sq_tail = nvmeq->sq_tail;

}

```




## 5. 中断响应路径

```c
nvme_irq()                                    // [第三步] CPU 硬件中断唤醒
  │
  ├── nvme_poll_cq(nvmeq, &iob)  // 轮询 CQ 提取结果
  │   │
  │   ├── while (nvme_cqe_pending):         // 循环检查 Phase bit 匹配
  │   │   ├── dma_rmb()           
  │   │   ├── nvme_handle_cqe()           // [第七步核心] 解析 16B CQE 
  |   |   |   ├── nvme_is_aen_req()     // 检查是否是 Async Event Notification
  │   │   │   ├── nvme_find_rq()        // 根据 command_id 找回 request 指针， request tag 与 SQE CID 和CQE CID 相同
  │   │   │   └── if(!nvme_try_complete_req() && !blk_mq_add_to_batch())
  │   │   │         // 记录 status 和 result |   放入 iob 链表 
  │   │   │           └── nvme_pci_complete_rq() 
  │   │   │               ├── nvme_pci_unmap_rq()    // 解映射 DMA 物理内存
  │   │   │               └── nvme_complete_rq()     
  │   │   │                   └── nvme_end_req()
  │   │   │                       └── blk_mq_end_request()
  │   │   │                           └── __blk_mq_end_request()  // 清除定时器
  │   │   │                               └── rq->end_io()
  │   │   │
  │   │   └── nvme_update_cq_head()       // cq_head 指针移动, 并且判断更新 cq_phase
  │   │
  │   └── if (found) nvme_ring_cq_doorbell()  // [第八步] writel 敲响 CQ DB 释放槽位
  │
  ├── if (!rq_list_empty(&iob.req_list)) // 顺序判断链表是否有挂载请求
  │   │
  │   └── nvme_pci_complete_batch(&iob)
  │       ├── nvme_pci_unmap_rq()    // 批量解映射 DMA 物理内存
  │       ├── nvme_complete_batch_req()   // 清理 req 相关命令，触发nvme内部 end 逻辑
  │       └── blk_mq_end_request_batch()  // 遍历 iob 链表中的每个 req:
  │           ├─── blk_complete_request()
  │           │    └── bio_endio()     
  │           │        └── bio->bi_end_io()
  │           └─── rq->end_io()      // 同一个req bio 先于 request 级 end_io
  │     
  │
  └── 阶段三：return IRQ_HANDLED                // 恢复 CPU 现场，退出中断
```



## 6. 驱动模块与sysfs分析


### 6.1 驱动模块参数
```bash
# 查看 /lib/modules/$(uname -r)/ nvme驱动信息
$ modinfo nvme

# 查看指定nvme.ko驱动信息
$ modinfo drivers/nvme/host/nvme.ko

$ modinfo drivers/nvme/host/nvme-core.ko

# 查看指定nvme.ko驱动参数
$ modinfo -p drivers/nvme/host/nvme.ko

# use_threaded_interrupts: (int)   开启线程化中断(驱动默认不开启---444)   
# use_cmb_sqes:use controller's memory buffer for I/O SQes (bool)   (驱动默认开启---444)
# max_host_mem_size_mb:Maximum Host Memory Buffer (HMB) size per controller (in MiB) (uint)     (驱动默认设置128---444)
# sgl_threshold:Use SGLs when average request segment size is larger or equal to this size. Use 0 to disable SGLs. (uint)  (驱动默认设置32KB---644)
# io_queue_depth:set io queue depth, should >= 2 and < 4096    (驱动默认设置1024---644)
# write_queues:Number of queues to use for writes. If not set, reads and writes will share a queue set.   (驱动默认设置0---644)
# poll_queues:Number of queues to use for polled IO.     (驱动默认设置0, 所有队列基于传统的硬件中断---644)
# noacpi:disable acpi bios quirks (bool)    (驱动默认设置disable---444)

# 查看指定nvme-core.ko驱动参数


# 查看线程化中断是否开启 (0代表关闭，1代表开启)
$ cat /sys/module/nvme/parameters/use_threaded_interrupts

# 查看是否启用了 CMB 内存缓冲区(Y代表开启，N代表关闭)
$ cat /sys/module/nvme/parameters/use_cmb_sqes

# 修改poll_queues (最好在启动项修改，以免只是软件修改硬件未同步)
$ echo 2 | sudo tee /sys/module/nvme/parameters/poll_queues
```




### 6.2 sysfs分析
`/sys/class/nvme/nvme0/` 来自于内核源码 `drivers/nvme/host/sysfs.c`，
  - 为/sys/devices/pci0000:00/0000:00:15.0/0000:03:00.0/nvme/nvme0的软链接

```bash
$ ls /sys/class/nvme/nvme0  
address    dev           kato   numa_node                 power/             serial     subsystem@
cntlid     device@       model  nvme0n1/                  queue_count        sqsize     transport
cntrltype  firmware_rev  ng0n1/ nvme0n2/                  rescan_controller  state      uevent
dctype     hwmon1/       ng0n2/ passthru_err_log_enabled  reset_controller   subsysnqn
```