# Phase 2 ESP32 串口探针实测记录

日期：2026-08-03

状态：串口工具链与物理重连切片通过；不代表第二阶段整体完成，也不代表产品固件功能验收通过。

## 设备与工具链

- 用户确认设备：ESP32 N16R8
- 实测芯片：ESP32-S3（QFN56，revision v0.2）
- 实测 PSRAM：8MB
- 串口：`/dev/cu.usbserial-10`
- USB 串口桥：VID `1A86`、PID `7523`
- Arduino CLI：1.5.1
- ESP32 Arduino core：3.3.10
- 编译配置：`esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,UploadSpeed=115200`

## 实测步骤与结果

1. 只读发现串口：通过；Arduino CLI 最初显示 USB-UART 端口为 `Unknown`，由用户确认板卡和端口后继续。
2. 编译临时串口探针：通过；程序大小 291109 bytes，动态内存 21916 bytes。
3. 上传：通过；bootloader、分区和应用镜像均写入并通过 hash 校验，随后硬复位。
4. 串口观察：通过；115200 baud 下收到连续输出：

   ```text
   KYROZEN_SERIAL_PROBE heartbeat 26
   KYROZEN_SERIAL_PROBE heartbeat 27
   KYROZEN_SERIAL_PROBE heartbeat 28
   KYROZEN_SERIAL_PROBE heartbeat 29
   KYROZEN_SERIAL_PROBE heartbeat 30
   ```

5. 拔插恢复：通过；重新插入后 `/dev/cu.usbserial-10` 恢复，并再次收到 `heartbeat 14` 至 `heartbeat 18`。
6. Ask question：用户确认“串口心跳行为符合预期，且拔插后已恢复”。

## 边界

本次刷入的是不使用 GPIO/LED 的临时串口探针，只证明 ESP32-S3 的串口编译、上传、观察和拔插恢复链路。它不能替代项目产品固件、LED/传感器接线、应用协议或完整硬件验收；这些必须在对应项目的正式固件和已确认目标行为下另行记录。
