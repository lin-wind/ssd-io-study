### PCIe
```
/sys/bus/pci/devices/0000:00:15.0  上游：PCIe 端口级链路状态
为/sys/devices/pci0000:00/0000:00:15.0的软连接

ls /sys/bus/pci/devices/0000:00:15.0   
0000:00:15.0:pcie001/     current_link_speed  irq             numa_node          resource
0000:00:15.0:pcie004/     current_link_width  link/           pci_bus/           revision
0000:03:00.0/             d3cold_allowed      local_cpulist   power/             secondary_bus_number
aer/                      device              local_cpus      power_state        subordinate_bus_number
ari_enabled               dma_mask_bits       max_link_speed  remove             subsystem@
broken_parity_status      driver@             max_link_width  rescan             subsystem_device
class                     driver_override     modalias        reset              subsystem_vendor
config                    enable              msi_bus         reset_method       uevent
consistent_dma_mask_bits  firmware_node@      msi_irqs/       reset_subordinate  vendor




/sys/bus/pci/devices/0000:00:15.0/0000:03:00.0   下游：NVMe 设备级链路状态

ls /sys/bus/pci/devices/0000:00:15.0/0000:03:00.0
acpi_index                current_link_width  irq             msi_bus      rescan        subsystem@
aer/                      d3cold_allowed      label           msi_irqs/    reset         subsystem_device
ari_enabled               device              link/           numa_node    reset_method  subsystem_vendor
broken_parity_status      dma_mask_bits       local_cpulist   nvme/        resource      uevent
class                     driver@             local_cpus      pools        resource0     vendor
config                    driver_override     max_link_speed  power/       resource2
consistent_dma_mask_bits  enable              max_link_width  power_state  revision
current_link_speed        firmware_node@      modalias        remove       rom



sudo lspci -s 00:15.0 -vvv
config配置文件

sudo lspci -s 03:00.0 -vvv
config配置文件

```


### MSI / MSI-X (Message Signaled Interrupts-Extended)

```
cat /proc/interrupts | grep nvme    
            CPU0       CPU1       CPU2       CPU3
  57:          0          0          0         97 PCI-MSIX-0000:03:00.0    0-edge      nvme0q0 (Admin队列)
  58:         45          0          0          0 PCI-MSIX-0000:03:00.0    1-edge      nvme0q1 (IO队列1)
  59:          0        100          0          0 PCI-MSIX-0000:03:00.0    2-edge      nvme0q2 (IO队列2)
  60:          0          0         90          0 PCI-MSIX-0000:03:00.0    3-edge      nvme0q3 (IO队列3)
  61:          0          0          0         38 PCI-MSIX-0000:03:00.0    4-edge      nvme0q4 (IO队列4)
  62:          0          0          0          0 PCI-MSIX-0000:03:00.0    5-edge      nvme0q5
  63:          0          0          0          0 PCI-MSIX-0000:03:00.0    6-edge      nvme0q6
  64:          0          0          0          0 PCI-MSIX-0000:03:00.0    7-edge      nvme0q7
  65:          0          0          0          0 PCI-MSIX-0000:03:00.0    8-edge      nvme0q8
  66:          0          0          0          0 PCI-MSIX-0000:03:00.0    9-edge      nvme0q9
  67:          0          0          0          0 PCI-MSIX-0000:03:00.0   10-edge      nvme0q10
  68:          0          0          0          0 PCI-MSIX-0000:03:00.0   11-edge      nvme0q11
  69:          0          0          0          0 PCI-MSIX-0000:03:00.0   12-edge      nvme0q12
  70:          0          0          0          0 PCI-MSIX-0000:03:00.0   13-edge      nvme0q13
  71:          0          0          0          0 PCI-MSIX-0000:03:00.0   14-edge      nvme0q14
  72:          0          0          0          0 PCI-MSIX-0000:03:00.0   15-edge      nvme0q15







```

### AER (Advanced Error Reporting)

static const struct pci_error_handlers nvme_err_handler = {
	.error_detected	= nvme_error_detected,    
	.slot_reset	= nvme_slot_reset,
	.resume		= nvme_error_resume,
	.reset_prepare	= nvme_reset_prepare,
	.reset_done	= nvme_reset_done,
};

- Correctable（可纠正）：硬件自己搞定，不回调通知驱动
- Non-Fatal（非致命）：通知驱动，链路没死，只报错不复位
- Fatal（致命）：通知驱动，链路已死，强制复位重置硬件

### ASPM (Active State Power Management)

```
cat /sys/module/pcie_aspm/parameters/policy
[default] performance powersave powersupersave 
```

### HotPlug



### FLR (function-levle reset)

.../0000:03:00.0/reset
 