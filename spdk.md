## SPDK
### fio引擎编译

```
$ git clone https://github.com/axboe/fio.git

$ ./configure

$ make -j$(nproc)

$ git clone https://github.com/spdk/spdk --recursive

$ ./configure --with-fio=$HOME/Desktop/fio   (也可以加上--enable-debug 进行函数调用分析)
Using default SPDK env in /home/users/Desktop/spdk/lib/env_dpdk
Using default DPDK in /home/users/Desktop/spdk/dpdk/build
Configuring ISA-L (logfile: /home/users/Desktop/spdk/.spdk-isal.log)...done.
Configuring ISA-L-crypto (logfile: /home/users/Desktop/spdk/.spdk-isal-crypto.log)...done.
Creating mk/config.mk...done.
Creating mk/cc.flags.mk...done.
Type 'make' to build.

$ make -j$(nproc)
```





```

struct ioengine_ops ioengine = {
	.name			= "spdk",
	.version		= FIO_IOOPS_VERSION,
	.queue			= spdk_fio_queue,
	.getevents		= spdk_fio_getevents,
	.event			= spdk_fio_event,
	.cleanup		= spdk_fio_cleanup,
	.open_file		= spdk_fio_open,
	.close_file		= spdk_fio_close,
	.invalidate		= spdk_fio_invalidate,
	.iomem_alloc		= spdk_fio_iomem_alloc,
	.iomem_free		= spdk_fio_iomem_free,
	.setup			= spdk_fio_setup,
	.init			= spdk_fio_init,
	.io_u_init		= spdk_fio_io_u_init,
	.io_u_free		= spdk_fio_io_u_free,
    /*...*/
	.options		= options,
	.option_struct_size	= sizeof(struct spdk_fio_options),
};
```






```
spdk_nvme引擎
/app/fio/nvme/fio_plugin.c

spdk_nvme额外的fio参数    (也可以通过fio_plugin.c 中struct fio_option options 查看)
$ sudo $HOME/Desktop/fio/fio --enghelp=$HOME/Desktop/spdk/build/fio/spdk_nvme  
enable_wrr              : Enable weighted round robin (WRR) for IO submission queues
enable_interrupts       : Enable interrupt mode, event FD and blocking poll
mem_size_mb             : Memory Size for SPDK (MB)
shm_id                  : Shared Memory ID
enable_sgl              : SGL Used for I/O Commands (enable_sgl=1 or enable_sgl=0)
sge_size                : SGL size in bytes for I/O Commands (default 4096)
hostnqn                 : Host NQN
log_flags               : Enable log flags (comma-separated list)
spdk_tracing            : SPDK Tracing (0=disable, 1=enable)
/*...*/

---

下发路径

const struct spdk_nvme_transport_ops pcie_ops = {
	.name = "PCIE",
	.type = SPDK_NVME_TRANSPORT_PCIE,
	.ctrlr_construct = nvme_pcie_ctrlr_construct,
	.ctrlr_create_io_qpair = nvme_pcie_ctrlr_create_io_qpair,
	.ctrlr_disconnect_qpair = nvme_pcie_ctrlr_disconnect_qpair,
	.qpair_submit_request = nvme_pcie_qpair_submit_request,
	.qpair_process_completions = nvme_pcie_qpair_process_completions,
    /*...*/
};


.setup (全局环境初始化与探测盘)        
  ├──   spdk_env_opts_init() &  spdk_env_init()   // 初始化 DPDK 大页与 VFIO/UIO 环境
  ├──  pthread_create(&g_ctrlr_thread_id, NULL, &spdk_fio_poll_ctrlrs, NULL)    // 启动后台 Admin 队列专用轮询线程
  └──  spdk_nvme_probe(...,probe_cb(),attach_cb(),...)     // 探测 PCIe NVMe 控制器，获取盘物理容量

.init (线程追踪注册) 【每个 Worker 线程独立执行】
  └──  spdk_trace_register_user_thread()    // 若开启 spdk_tracing=1 则注册线程 tracepoint
  
.io_u_init (预分配每个 I/O 的私有上下文)    【每个 Worker 线程循环 iodepth 次】
  ├──   calloc(fio_req)
  ├──   calloc(dsm_size)
  └──   spdk_dma_zmalloc()
  
.iomem_alloc (分配DMA大页)    
  ├──  spdk_nvme_ctrlr_get_numa_id()    // 获取目标盘所在 NUMA 节点
  └──  spdk_dma_zmalloc_socket()       // 在同 NUMA 节点上一次性向 SPDK 申请锁定大页数据池
  
.open_file (探测打开NVMe盘)   
  └── spdk_nvme_ctrlr_alloc_io_qpair()  // 向 SSD 控制器申请分配本线程独占的 SQ/CQ 硬件队列




spdk_fio_queue()                                  [fio 插件层]
  |    enable_sgl = 1
  └── spdk_nvme_ns_cmd_writev_with_md(..., spdk_fio_completion_cb, ...)  //回调函数 spdk_fio_completion_cb()        
      ├── _nvme_ns_cmd_rw_req_init_sgl()          // 分配请求
      ├── _nvme_ns_cmd_rw()                       // 内部组装/拆分命令
      │   └── _nvme_ns_cmd_setup_request()       // 填 64B SQE 结构
      │
      └── nvme_qpair_submit_request()             // 提交进通用 qpair 队列
          └── _nvme_qpair_submit_request()               
              |    (若有子请求则遍历 children 递归调用 nvme_qpair_submit_request())   
              |
              └── nvme_transport_qpair_submit_request() 
                  |     qpair->transport->ops.qpair_submit_request()
                  |
                  └── nvme_pcie_qpair_submit_request() 
                      ├── g_nvme_pcie_build_req_table      // 构造 PRP/SGL DMA 
                      |     nvme_pcie_qpair_build_prps_sgl_request() .. 4种情况
                      |  
                      |
                      └── nvme_pcie_qpair_submit_tracker() 
                          ├── nvme_pcie_copy_command      //   将 64B SQE 写入 SQ Ring Buffer
                          └── nvme_pcie_qpair_ring_sq_doorbell() 
                              └── spdk_mmio_write_4      //  敲硬件 Doorbell 寄存器

spdk_fio_event()

spdk_fio_getevents()
  |
  ├── spdk_nvme_qpair_process_completions()
  |    |
  |    └── nvme_transport_qpair_process_completions()
  |        |   qpair->transport->ops.qpair_process_completions()
  |        |
  |        └── nvme_pcie_qpair_process_completions()
  |            |
  |            ├── nvme_pcie_qpair_complete_tracker()
  |            |   └── nvme_complete_request()
  |            |       |   cb_fn(cb_arg, cpl)     回调
  |            |       └── spdk_fio_completion_cb()
  |            |
  |            └── nvme_pcie_qpair_ring_cq_doorbell()
  |                └── spdk_mmio_write_4   //  敲硬件 Doorbell 寄存器
  |
  |
  └── fio_thread->iocq_count



.close_file (关闭设备与销毁硬件队列)  【每个 Worker 线程执行 1 次】
  └── spdk_nvme_ctrlr_free_io_qpair()          // 向 SSD 发送删除 SQ/CQ 指令，释放本线程独占的硬件队列

.io_u_free (释放每个 I/O 的私有上下文) 【每个 Worker 线程循环 iodepth 次】
  ├── spdk_dma_free(fio_req->md_buf)           // 释放每个 io_u 预分配的 4KB DMA 元数据内存
  ├── free(fio_req->dsm_range)                 // 释放 Trim 范围描述符
  └── free(fio_req)                            // 释放请求控制块结构体

.iomem_free (释放 DMA 锁定大页内存)   【每个 Worker 线程执行 1 次】
  └── spdk_dma_free(td->orig_buffer)           // 将本线程的整块数据缓冲区归还给 SPDK 大页内存池

.cleanup (线程资源清理与控制器断开)   【每个 Worker 线程执行 1 次】
  ├── spdk_trace_unregister_user_thread     // 若开启 spdk_tracing=1
  ├── free(fio_thread->iocq) & free(fio_thread)// 释放本线程的完成事件数组
  ├── g_td_count--                             // 活跃线程计数减 1
  └── 【当最后一个线程退出时: g_td_count == 0】
       ├── spdk_nvme_detach_async()            // 断开与 NVMe 物理盘的 PCIe 控制器连接
       └── pthread_cancel(g_ctrlr_thread_id)   // 终止并回收第 0 步创建的后台 Admin 队列轮询线程
       
fio_exit (fio_spdk_unregister进程退出注销)               【fio 进程退出时执行 1 次】
  └── spdk_env_fini()                          // 注销 DPDK/SPDK 全局运行环境与大页锁

```



![](image/spdk/download.svg)



```
spdk_bdev引擎
/app/fio/bdev/fio_plugin.c
```