import asyncio
#import concurrent.features
import serial_asyncio
import serial
import logging
import time
import copy
import rrdtool
import os

FORMAT = '%(asctime)-15s {%(filename)s:%(lineno)d} %(levelname)s - %(message)s'
logging.basicConfig(format=FORMAT)
log = logging.getLogger('pi')
log.setLevel(logging.INFO)

sleep_bytes = bytearray([0x42, 0x4d, 0xe4, 0x00, 0x00, 0x01, 0x73])
wakeup_bytes = bytearray([0x42, 0x4d, 0xe4, 0x00, 0x01, 0x01, 0x74])

FRAME_SZ = 32
REFRESH_SEC = 3 # 60


class Measurement:
    def __init__(self, m_0_cf1, m2_5_cf1, m10_0_cf1, m1_0_atmo, m2_5_atmo,
                 m10_0_atmo, m0_3_ct, m0_5_ct, m1_0_ct, m2_5_ct, m5_0_ct, m10_0_ct):
        self.pm1_0_cf1 = m1_0_cf1
        self.pm2_5_cf1 = m2_5_cf1
        self.pm10_0_cf1 = m10_0_cf1
        self.pm1_0_atmo = m1_0_atmo
        self.pm2_5_atmo = m2_5_atmo
        self.pm10_0_atmo = m10_0_atmo
        self.pm0_3_ct = m0_3_ct
        self.pm0_5_ct = m0_5_ct
        self.pm1_0_ct = m1_0_ct
        self.pm2_5_ct = m2_5_ct
        self.pm5_0_ct = m5_0_ct
        self.pm10_0_ct = m10_0_ct


class Monitor(asyncio.Protocol):
    def __init__(self):
        asyncio.Protocol.__init__(self)
        self.data_ = bytearray()
        if not os.path.exists("pm_2_5_ct.rrd"):
            rrdtool.create("pm_2_5_ct.rrd", "--no-overwrite", "--start", "now", "--step", "5",
                       "RRA:AVERAGE:0.5:1:600",
                       "RRA:AVERAGE:0.5:1:600",
                       "DS:pm_2_5_ct:GAUGE:60:0:65536")

    def connection_made(self, transport):
        self.transport = transport
        log.info('port opened')
        transport.serial.rts = False
        transport.write(wakeup_bytes)

    def data_received(self, data):
        log.debug('data received %d %s', len(data), repr(data))
        if data == b'\x42':
            log.debug("frame %d %s", len(self.data_), repr(self.data_))
            if self.data_ and len(self.data_) >= FRAME_SZ:
                frame_data = copy.copy(self.data_)
                asyncio.ensure_future(self.process(frame_data))
                self.data_ = bytearray()
                self.data_ += data
                asyncio.ensure_future(self.do_sleep())
        else:
            self.data_ += data

    async def do_sleep(self):
        self.transport.write(sleep_bytes)
        # time.sleep(REFRESH_SEC)
        await asyncio.sleep(REFRESH_SEC)
        self.transport.write(wakeup_bytes)
        
    async def process(self, data):
        log.info("%d %s", len(data), repr(data))
        if data[0] != 0x42 or data[1] != 0x4d:
            log.info("skipping %s %s %s", repr(data), data[0], data[1])
            return
        frame_len = (data[2] << 8) + data[3]
        data = data[4:frame_len]

        higher = data[::2]
        lower = data[1::2]
        proc_data = [(d1 << 8) + d2 for d1, d2 in zip(higher, lower)]
        if len(proc_data) != 12:
            log.info("aaa  %s", repr(data))
        log.info("%d %s", len(proc_data), proc_data)
        rrdtool.update("pm_2_5_ct.rrd", "N:%d" % (proc_data[9]))
        
    def connection_lost(self, exc):
        log.info('port closed')
        asyncio.get_event_loop().stop()


loop = asyncio.get_event_loop()
coro = serial_asyncio.create_serial_connection(loop,
                                               Monitor,
                                               '/dev/serial0',
                                               baudrate=9600)
transport, protocol = loop.run_until_complete(coro)
loop.run_forever()
loop.close()

# asyncio.run(main())
