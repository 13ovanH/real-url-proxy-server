#!/opt/bin/python3

#-------------------------------------------------------------------------------
# Name:        real-url-proxy-server
# Purpose:     A proxy server to extract real url of DouYu and HuYa live room
#
# Author:      RAiN
#
# Created:     05-03-2020
# Copyright:   (c) RAiN 2020
# Licence:     GPL
#-------------------------------------------------------------------------------

import sys
from abc import ABCMeta, abstractmethod
from http.server import SimpleHTTPRequestHandler
from http.server import HTTPServer
from socketserver import ThreadingMixIn
import functools
from threading import Timer
import argparse
from datetime import datetime
from douyu import DouYu
from huya import huya

class RealUrlExtractor:
    __metaclass__ = ABCMeta

    def __init__(self, room, auto_refresh, auto_refresh_timespan):
        self.room = room
        self.real_url = None
        self.auto_refresh = auto_refresh
        self.auto_refresh_timespan = auto_refresh_timespan
        self.last_refresh_time = datetime.min

    @abstractmethod
    def _extract_real_url(self):
        self.last_refresh_time = datetime.now()

    def get_real_url(self, bit_rate):
        if self.real_url is None or bit_rate == 'refresh' or (self.auto_refresh and (datetime.now() - self.last_refresh_time).seconds >= self.auto_refresh_timespan):
            self._extract_real_url()

class HuYaRealUrlExtractor(RealUrlExtractor):
    def _extract_real_url(self):
        self.real_url = huya(self.room)
        super()._extract_real_url()

    def get_real_url(self, bit_rate):
        super().get_real_url(bit_rate)

        if bit_rate == 'refresh':
            bit_rate = None

        if self.real_url is None or not isinstance(self.real_url, dict):
            return None
        if bit_rate is None or len(bit_rate) == 0:
            return self.real_url['BD']
        if bit_rate in self.real_url.keys():
            return self.real_url[bit_rate]
        return None

class DouYuRealUrlExtractor(RealUrlExtractor):
    def _extract_real_url(self):
        try:
            self.real_url = DouYu(self.room).get_real_url()
        except:
            self.real_url = 'None'
        super()._extract_real_url()

    def get_real_url(self, bit_rate):
        super().get_real_url(bit_rate)

        if bit_rate == 'refresh':
            bit_rate = None

        if self.real_url == 'None':
            return None;
        if bit_rate is None or len(bit_rate) == 0:
            return self.real_url
        return self.real_url.replace('.flv?', '_' + bit_rate + '.flv?')

class RealUrlRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, processor_maps, **kwargs):
        self.processor_maps = processor_maps
        super().__init__(*args, **kwargs)

    def do_GET(self):
        s = self.path[1:].split('/')
        if len(s) >= 2:
            provider = s[0]
            room = s[1]
            if len(s) > 2:
                bit_rate = s[2]
            else:
                bit_rate = None
            print('provider: %s, room: %s, bit_rate: %s' % (provider, room, bit_rate))

            if provider == 'douyu':
                if provider not in self.processor_maps.keys():
                    self.processor_maps[provider] = {}
                douyu_processor_map = self.processor_maps[provider]

                try:
                    if room not in douyu_processor_map.keys():
                        douyu_processor_map[room] = DouYuRealUrlExtractor(room, False, 0)

                    real_url = douyu_processor_map[room].get_real_url(bit_rate)
                    if real_url is not None:
                        self.send_response(301)
                        self.send_header('Location', real_url)
                        self.end_headers()
                        return
                except Exception as e:
                    print("Failed to extract douyu real url! Error: %s" % (str(e)))
            elif provider == 'huya':
                if provider not in self.processor_maps.keys():
                    self.processor_maps[provider] = {}
                huya_processor_map = self.processor_maps[provider]

                try:
                    if room not in huya_processor_map.keys():
                        huya_processor_map[room] = HuYaRealUrlExtractor(room, True, 3600 * 2)

                    real_url = huya_processor_map[room].get_real_url(bit_rate)
                    if real_url is not None:
                        m3u8_content = '#EXTM3U\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1\n' + real_url
                        self.send_response(200)
                        self.send_header('Content-type', "application/vnd.apple.mpegurl")
                        self.send_header("Content-Length", str(len(m3u8_content)))
                        self.end_headers()
                        self.wfile.write(m3u8_content.encode('utf-8'))
                        return
                except Exception as e:
                    print("Failed to extract huya real url! Error: %s" % (str(e)))

        rsp = "Not Found"
        rsp = rsp.encode("gb2312")

        self.send_response(404)
        self.send_header("Content-type", "text/html; charset=gb2312")
        self.send_header("Content-Length", str(len(rsp)))
        self.end_headers()
        self.wfile.write(rsp)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='A proxy server to get real url of live providers.')
    parser.add_argument('-p', '--port', type=int, required=True, help='Binding port of HTTP server.')
    args = parser.parse_args()

    processor_maps = {}
    HandlerClass = functools.partial(RealUrlRequestHandler, processor_maps=processor_maps)
    ServerClass  = ThreadingHTTPServer
    #Protocol     = "HTTP/1.0"

    server_address = ('0.0.0.0', args.port)

    #HandlerClass.protocol_version = Protocol
    httpd = ServerClass(server_address, HandlerClass)

    sa = httpd.socket.getsockname()
    print("Serving HTTP on", sa[0], "port", sa[1], "...")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

    httpd.server_close()
    print("Server stopped.")