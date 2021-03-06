import socket
import logging
from time import time, sleep

from ogn.client import settings


def create_aprs_login(user_name, pass_code, app_name, app_version, aprs_filter=None):
    if not aprs_filter:
        return "user {} pass {} vers {} {}\n".format(user_name, pass_code, app_name, app_version)
    else:
        return "user {} pass {} vers {} {} filter {}\n".format(user_name, pass_code, app_name, app_version, aprs_filter)


class AprsClient:
    def __init__(self, aprs_user, aprs_filter='', settings=settings):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Connect to OGN as {} with filter '{}'".format(aprs_user, (aprs_filter if aprs_filter else 'full-feed')))
        self.aprs_user = aprs_user
        self.aprs_filter = aprs_filter
        self.settings = settings

        self._kill = False

    def connect(self):
        # create socket, connect to server, login and make a file object associated with the socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        if self.aprs_filter:
            port = self.settings.APRS_SERVER_PORT_CLIENT_DEFINED_FILTERS
        else:
            port = self.settings.APRS_SERVER_PORT_FULL_FEED

        self.sock.connect((self.settings.APRS_SERVER_HOST, port))
        self.logger.debug('Server port {}'.format(port))

        login = create_aprs_login(self.aprs_user, -1, self.settings.APRS_APP_NAME, self.settings.APRS_APP_VER, self.aprs_filter)
        self.sock.send(login.encode())
        self.sock_file = self.sock.makefile('rw')

        self._kill = False

    def disconnect(self):
        self.logger.info('Disconnect')
        try:
            # close everything
            self.sock.shutdown(0)
            self.sock.close()
        except OSError:
            self.logger.error('Socket close error', exc_info=True)

        self._kill = True

    def run(self, callback, timed_callback=lambda client: None, autoreconnect=False):
        while not self._kill:
            try:
                keepalive_time = time()
                while not self._kill:
                    if time() - keepalive_time > self.settings.APRS_KEEPALIVE_TIME:
                        self.logger.info('Send keepalive')
                        self.sock.send('#keepalive\n'.encode())
                        timed_callback(self)
                        keepalive_time = time()

                    # Read packet string from socket
                    packet_str = self.sock_file.readline().strip()

                    # A zero length line should not be return if keepalives are being sent
                    # A zero length line will only be returned after ~30m if keepalives are not sent
                    if len(packet_str) == 0:
                        self.logger.warning('Read returns zero length string. Failure.  Orderly closeout')
                        break

                    callback(packet_str)
            except ConnectionError:
                self.logger.error('ConnectionError', exc_info=True)
            except socket.error:
                self.logger.error('socket.error', exc_info=True)
            except UnicodeDecodeError:
                self.logger.error('UnicodeDecodeError', exc_info=True)

            if autoreconnect and not self._kill:
                self.connect()
            else:
                return


class TelnetClient:
    def __init__(self, settings=settings):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Connect to local telnet server")
        self.settings = settings

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.settings.TELNET_SERVER_HOST, self.settings.TELNET_SERVER_PORT))

    def run(self, callback, autoreconnect=False):
        while True:
            try:
                self.sock_file = self.sock.makefile(mode='rw', encoding='iso-8859-1')
                while True:
                    packet_str = self.sock_file.readline().strip()
                    callback(packet_str)

            except ConnectionRefusedError:
                self.logger.error('Telnet server not running', exc_info=True)

            if autoreconnect:
                sleep(1)
                self.connect()
            else:
                return

    def disconnect(self):
        self.logger.info('Disconnect')
        self.sock.shutdown(0)
        self.sock.close()
