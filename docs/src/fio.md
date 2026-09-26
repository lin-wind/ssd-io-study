# fio

## parameter

- `direct= ` :使用数字1，表示直接I/O (Direct I/O)，绕过操作系统的Page Cache
- `ioengine= ` :I/O提交给内核的方式
  - libaio    传统企业级测试，业界标准。多种数据库大多使用异步I/O
  - io_uring    高性能NVMe测试，现代首选。比libaio系统调用开销更低
  - psync   单线程/简单验证，同步I/O。通常用于测试简单的文件拷贝性能，不适合测并发极限
  - spdk    极致/开发测试(需要fio插件)完全绕过内核，直接在用户态操作NVMe寄存器。我们在调试FW性能瓶颈时使用。
- `io_size= `
- `thread= ` : 模拟并发 spdk下thread必须开启
- `iodepth= ` : 每个Job在队列中保持的I/O数量
- `numjobs= ` : 并发的Job数量，Total QD总并发= iodepth * numjobs
  - 低QD(QD1-4)测试延迟
  - 高QD(QD32-128+)测试吞吐量
- `bs= ` : Block Size每次IO读写的数据块大小
  - 4k : 对齐NAND Page的最小物理单元
  - 128/1m : 模拟大文件传输，测试顺序读写带宽
  - 3k : 非对齐测试，强制SSD进行“读-改-写”（Read-Modify-Write）
- `rw= ` : Read/Write Pattern
  - read
  - write
  - randread
  - randwrite
  - rw(混合顺序)
  - randrw
- `rwmixread/rwmixwrite= ` 混合模式中的读写百分比
- `runtime= & time_based` 强制运行时间
- `ramp_time= ` 记录数据前的预热时间
- `hipri=1` : 使用poll completion,必须搭配io_uring
- `fixedbufs=1`:预映射页面，搭配io_uring
- `registerfiles=1`:备案fd给内核，必须搭配sqthread_poll
- `sqthread_poll=1` poll sq 
- `percentile_list= `
- `verify=`: 数据完整性校验
- `steadystate= `: 稳态
- `norandommap=1` 允许重复写入同一个块，和参数verify冲突

