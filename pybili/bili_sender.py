#!/usr/bin/python
# coding=utf-8
import requests
import ocr
import json
import time
import sys
import thread
import logging
import logging.handlers
import os.path
import pybili
import traceback
from PIL import Image
import StringIO

LOGIN_CHECK_URL = 'http://api.live.bilibili.com/User/getUserInfo'
SEND_URL = 'http://live.bilibili.com/msg/send'
TV_URL = 'http://api.live.bilibili.com/gift/v2/smalltv/join'
QUERY_RAFFLE_URL = 'http://api.live.bilibili.com/activity/v1/Raffle/check'
RAFFLE_URL = 'http://api.live.bilibili.com/activity/v1/Raffle/join'
QUERY_FREE_SILVER = 'http://api.live.bilibili.com/lottery/v1/SilverBox/getCurrentTask'
GET_FREE_SILVER = 'http://api.live.bilibili.com/lottery/v1/SilverBox/getAward'
CAPTCHA_URL = 'http://api.live.bilibili.com/lottery/v1/SilverBox/getCaptcha?ts=%i'
SIGN_IN_URL = ''
GET_SIGN_INFO_URL = 'http://api.live.bilibili.com/sign/GetSignInfo'
GET_USER_INFO_URL = 'http://live.bilibili.com/user/getuserinfo'


class Sender(object):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36',
        'Host': 'api.live.bilibili.com',
    }

    def _initLogger(self, logger):
        logger.setLevel(pybili.__loglevel__)
        ch = logging.handlers.TimedRotatingFileHandler(os.path.join(pybili.__workdir__, 'bili_sender.log'),
                                                       when='midnight')
        logger.addHandler(ch)
        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # add formatter to ch
        ch.setFormatter(formatter)
        logger.info('logger bili_sender init success')

    def __init__(self, cookies):
        logger = logging.getLogger('bili_sender')
        if not logger.handlers:
            self._initLogger(logger)
        self.logger = logger

        self.cookies = cookies
        self.checkLogin()
        self.lightenIds = set()
        self.raffleIds = set()

    def _get(self, url, params=None, headers=None):
        try:
            headers = headers if headers else {}
            cookies = '; '.join([
                '%s=%s' % (key, val) for key, val in self.cookies.iteritems()
            ])
            headers['Cookie'] = cookies
            r = requests.post(url, data=params, cookies=self.cookies, headers=self.headers)
            return self._parseHttpResult(url, r)
        except Exception as e:
            self.logger.error("HTTP GET REQ %s fail!" % url)

    def _post(self, url, params=None, headers=None):
        try:
            headers = headers if headers else {}
            cookies = '; '.join([
                '%s=%s' % (key, val) for key, val in self.cookies.iteritems()
            ])
            headers['Cookie'] = cookies
            r = requests.post(url, data=params, cookies=self.cookies, headers=self.headers)
            return self._parseHttpResult(url, r)
        except Exception as e:
            self.logger.error("HTTP POST REQ %s fail!" % url)

    def _parseHttpResult(self, url, r):
        result = r.content
        raw = json.loads(result)
        self.logger.debug(raw)
        if raw['code'] != 0:
            self.logger.warn("API %s fail! MSG: %s" % (url, raw['msg']))

        if raw['code'] == 65531:
            self.logger.warn("API %s fail! WRONG HEADER!" % (url))
        elif raw['code'] != 0 and raw['code'] != 'REPONSE_OK':
            self.logger.warn("API %s fail! MSG: %s" % (url, raw['msg']))
        return raw

    def checkLogin(self):
        r = self._get(LOGIN_CHECK_URL)
        if r and r['code'] == 'REPONSE_OK':
            print u'Login Success'
        else:
            print u'Login Failed'

    def isCookieValid(self):
        raw = self._get(GET_USER_INFO_URL)
        if raw['code'] != 0 and raw['code'] != 'REPONSE_OK':
            return raw['msg']
        else:
            uname = raw['data']['uname']
            return 'OK, welcome %s' % uname

    def signIn(self):
        return self._get(SIGN_IN_URL)

    def sendDanmaku(self, roomid, content, color='white'):
        content = content.strip()
        if not content: return
        if color == 'blue':
            color = 6737151
        elif color == 'green':
            color = 8322816
        else:
            color = 16777215  # white
        params = {
            "color": color,
            "fontsize": 25,
            "mode": 1,
            "msg": content,
            "rnd": int(time.time()),
            "roomid": roomid
        }
        return self._post(SEND_URL, params)

    def joinSmallTV(self, roomid, tv_id):
        params = {
            'roomid': roomid,
            'raffleId': tv_id,
            '_': int(time.time() * 100)
        }
        print u'Join %s SmallTV' % roomid

        self._get(TV_URL, params)

    def _joinRaffle(self, roomid, raffleId):
        room_data = self._get('http://api.live.bilibili.com/room/v1/Room/room_init?id=%s' % roomid)['data']
        self.headers['Referer'] = 'http://live.bilibili.com/%s' % (
            room_data['short_id'] if room_data['short_id'] != 0 else room_data['room_id'])

        params = {
            'roomid': int(roomid),
            'raffleId': raffleId
        }
        headers = {
            'Host': 'api.live.bilibili.com',
            'Origin': 'http://live.bilibili.com',
            'Referer': 'http://live.bilibili.com/%s' % roomid,
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.13; rv:57.0) Gecko/20100101 Firefox/57.0'
        }
        r = self._get(RAFFLE_URL, params, headers=self.headers)
        if r:
            self.logger.debug('join raffle: %s' % r['msg'])

    def joinRaffle(self, roomid, giftId):
        params = {
            'roomid': roomid
        }
        r = self._get(QUERY_RAFFLE_URL, params)
        if r:
            for d in r['data']:
                raffleId = d['raffleId']
                if raffleId not in self.raffleIds:
                    print u'Join %s Raffle' % roomid
                    self._joinRaffle(roomid, raffleId)
                    self.raffleIds.add(raffleId)
                    thread.start_new_thread(self.checkRaffle, (roomid, raffleId))

    def checkRaffle(self, roomid, raffleId):
        try:
            re_check = True
            while re_check:
                re_check = False
                time.sleep(60)
                url = 'http://api.live.bilibili.com/activity/v1/Raffle/notice'
                params = {
                    'roomid': roomid,
                    'raffleId': raffleId
                }
                r = self._get(url, params)
                if r and r['data']:
                    if r['data']['gift_id'] > 0:
                        print u'Get Raffle'
                        self.logger.info('get!name:%s, cnt:%d' % (r['data']['gift_name'], r['data']['gift_num']))
                    elif r['data']['gift_id'] == -1:
                        self.logger.info('empty!')
                    else:
                        self.logger.warn(r)
                else:
                    re_check = True
        except Exception as e:
            self.logger.exception(e)

    def checkFreeSilver(self):
        while 1:
            try:
                sleepTime = self.queryFreeSilver()
                self.logger.info('queryFreeSilver sleep %ds' % sleepTime)
                time.sleep(sleepTime)
            except Exception as error:
                self.logger.warn('query free silver fail!')
                self.logger.exception(error)

            time.sleep(10)

    def downloadCaptcha(self):
        t = int(time.time() * 1000)
        r = requests.get(CAPTCHA_URL % t, cookies=self.cookies)
        imgBuf = StringIO.StringIO(r.content)  # 采用StringIO直接将验证码文件写到内存，省去写入硬盘
        img = Image.open(imgBuf)  # PIL库加载图片
        return img

    def getFreeSilver(self, data):
        self.logger.info('downloadCaptcha...')
        img = self.downloadCaptcha()
        captcha = ocr.recognize(img)
        self.logger.info('captcha: %d' % captcha)
        params = {
            'time_start': data['time_start'],
            'end_time': data['time_end'],
            'captcha': captcha
        }
        r = self._get(GET_FREE_SILVER, params)
        if r['code'] == 0: self.logger.info('get %d silver coins' % r['data']['awardSilver'])

    def queryFreeSilver(self):
        r = self._get(QUERY_FREE_SILVER)
        # {"code":0,"msg":"","data":{"minute":3,"silver":30,"time_start":1509638833,"time_end":1509639013,"times":1,"max_times":3}}
        if r:
            if r['code'] == -10017:
                self.logger.info('all free silver coins today have been catched!')
                return 3600 * 2
            cur = time.time()
            if r['data']['time_end'] < cur:
                self.getFreeSilver(r['data'])
                return 180
            print u'%s later get FreeSilver' % int(r['data']['time_end'] - cur)
            return int(r['data']['time_end'] - cur)

    def startFreeSilverThread(self):
        print 'init ocr function...'
        try:
            global ocr
            import ocr
            if self.cookies:
                print 'checking free silver coins...'
                thread.start_new_thread(self.checkFreeSilver, ())
        except:
            self.logger.error('cannot start checkFreeSilver thread')


def main():
    import bili_config
    argv = sys.argv
    config = bili_config.Config()
    sender = Sender(config.cookies)
    sender.startFreeSilverThread()
    while 1:
        content = raw_input()
        sender.sendDanmaku(int(argv[1]), content)


if __name__ == '__main__':
    main()
