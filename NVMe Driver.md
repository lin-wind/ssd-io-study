### NVMe Driver

### 下载源码编译驱动
驱动基于6.17.0-41-generic 环境 24.04.1-Ubuntu

`sudo apt update `

`apt-get source linux-hwe-6.17`
提示
Reading package lists... Done
E: You must put some 'deb-src' URIs in your sources.list


修改配置文件
`sudo sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources`

`sudo apt update `

`apt-get source linux-hwe-6.17`
查看/debian/changelog或者是下载的.dsc发现为Main version: 6.17.0-41.41~24.04.1
升级本地ubuntu 内核到-41
`sudo apt install linux-image-6.17.0-41-generic linux-headers-6.17.0-41-generic`
`sudo reboot`


查看相关依赖是否安装
`dpkg -l build-essential libncurses-dev bison flex libssl-dev libelf-dev libdw-dev dwarves`
安装对应包
`sudo apt install -y build-essential libncurses-dev bison flex libssl-dev libelf-dev libdw-dev dwarves `


在对应根目录下进行模块编译配置
`make menuconfig`

`make olddefconfig && make prepare`

`make -C /lib/modules/6.17.0-41-generic/build M=$PWD/drivers/nvme/host modules`(修改代码重新编译使用此命令)

编译出对应nvme.ko nvme-fabrics.ko nvme-fc.ko nvme-core.ko等等文件

```
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


# 查看对应参数
# 查看线程化中断是否开启 (0代表关闭，1代表开启)
$ cat /sys/module/nvme/parameters/use_threaded_interrupts

# 查看是否启用了 CMB 内存缓冲区(Y代表开启，N代表关闭)
$ cat /sys/module/nvme/parameters/use_cmb_sqes

# 修改poll_queues (最好在启动项修改，以免只是软件修改硬件未同步)
$ echo 2 | sudo tee /sys/module/nvme/parameters/poll_queues

```

临时卸载对应驱动(先卸载nvme再卸载它的依赖nvme_core)系统盘不能在nvme盘上否则崩溃
`sudo rmmod nvme`
`sudo rmmod nvme_core`

临时加载对应驱动(先加载core再加载nvme, 可附带参数)
`sudo insmod nvme_core.ko`
`sudo insmod nvme.ko`
`sudo insmod nvme.ko poll_queues=2 io_queue_depth=512`

`lsmod | grep nvme`

加载原先 `/lib/modules`的驱动
`sudo modprobe nvme`

```



# 创建一个静态变量，默认设置为0
static bool my_debug_mode = false;
# 创造功能开关：将其注册为内核模块参数，类型为 bool，权限为 0644
module_param(my_debug_mode, bool, 0644);
# 编写说明书：让 modinfo 能够识别并打印这段解释
MODULE_PARM_DESC(my_debug_mode, "Enable my custom NVMe driver deep debug logging (default: false)");

# 可以通过实时修改或者驱动加载时修改参数，查看打印信息
echo 1 | sudo tee /sys/module/nvme/parameters/my_debug_mode

# 打印信息
if (my_debug_mode) {
    dev_info(dev->dev, "MY_DEBUG: INFO!\n");
}

```



```

$ cat /proc/sys/kernel/printk
4 4 1 7

控制台小于 4 打印
默认消息等级为 4
第一个数字最小为 1
出厂控制台等级为 7

0 emergency 1 alert 2 critical 3 error 4 warning 5 notice 6 info 7 debug

```

### sysfs分析

```
/sys/class/nvme/nvme0/ 来自于内核源码/drivers/nvme/host/sysfs.c
为/sys/devices/pci0000:00/0000:00:15.0/0000:03:00.0/nvme/nvme0的软链接


$ ls /sys/class/nvme/nvme0  
address    dev           kato   ng0n3/     nvme0n3/                  rescan_controller  state      uevent
cntlid     device@       model  numa_node  passthru_err_log_enabled  reset_controller   subsysnqn
cntrltype  firmware_rev  ng0n1/ nvme0n1/   power/                    serial             subsystem@
dctype     hwmon1/       ng0n2/ nvme0n2/   queue_count               sqsize             transport

```


### 结构体分析

```
# 结构体 nvme_dev

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
    /*...*/

};

# 结构体 nvme_queue

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
    /*...*/
};

# 结构体 nvme_iod

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


# 结构体 nvme_ctrl

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
    /*...*/

};
```






### NVMe内核模块

```core.c```
```
static const struct file_operations nvme_dev_fops = {
	.owner		= THIS_MODULE,
	.open		= nvme_dev_open,
	.release	= nvme_dev_release,
	.unlocked_ioctl	= nvme_dev_ioctl,
	.compat_ioctl	= compat_ptr_ioctl,
	.uring_cmd	= nvme_dev_uring_cmd,
};


```


```pci.c```

```
[module_init] --> nvme_init()
-> pci_register_driver(&nvme_driver)

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

[module_exit] --> nvme_exit()
-> pci_unregister_driver(&nvme_driver)
```

- nvme_probe()
- nvme_remove()
- nvme_shutdown()



```
static const struct pci_error_handlers nvme_err_handler = {
	.error_detected	= nvme_error_detected,    
	.slot_reset	= nvme_slot_reset,
	.resume		= nvme_error_resume,
	.reset_prepare	= nvme_reset_prepare,
	.reset_done	= nvme_reset_done,
};
```



---

nvme_ctrl_state
- NVME_CTRL_NEW 0
- NVME_CTRL_LIVE
- NVME_CTRL_RESETTING
- NVME_CTRL_CONNECTING
- NVME_CTRL_DELETING
- NVME_CTRL_DELETING_NOIO
- NVME_CTRL_DEAD




```

nvme_probe()
    -> nvme_pci_alloc_dev()
    -> nvme_add_ctrl()
    -> nvme_dev_map()
    -> nvme_pci_alloc_iod_mempool()
    -> nvme_pci_enable()
        -> enable PCI
        -> read CAP/CSTS
        -> configure admin queue
    -> nvme_alloc_admin_tag_set()
    -> nvme_change_ctrl_state()
    -> NEW -> CONNETING
    -> nvme_init_ctrl_finish()
        -> identify controller
    -> nvme_ctrl_meta_sgl_supported()
    -> nvme_dbbuf_dma_alloc()
    -> nvme_setup_host_mem()
    -> nvme_update_attrs()
    -> nvme_setup_io_queues()
        -> set queue count
        -> setup IRQs
        -> create IO SQ/CQ
    -> nvme_alloc_io_tag_set()
        -> connect to blk-mq
    -> nvme_dbbuf_set()
    -> nvme_change_ctrl_state()
    -> CONNECTING -> LIVE
    -> pci_set_drvdata()
    -> nvme_start_ctrl()
    -> nvme_put_ctrl()
    -> flush_work()

```


一次调用nvme_queue_rq()队列只写入一个SQE，最大传输数据(最小内存页大小 MPSMIN * 2^MDTS)(mpsmin一般为4KB也能大页内存2mb)

           
---

### NVMe处理命令步骤
- 主机写命令到 SQ
- 主机写 SQ 的 DB，通知 SSD 取指
- SSD 收到通知后， 到 SQ 取指
- SSD 执行指令
- 指令执行完成， SSD 往 CQ中写指令执行结果
- SSD发中断通知主机指令完成
- 收到中断，主机处理 CQ，查看指令完成状态
- 主机处理完 CQ 中的指令执行结果，通过 DB 回复 SSD


```
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



```


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


---




```
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

