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

LOGIN_CHECK_URL = 'http://api.live.bilibili.com/User/getUserInfo'
SEND_URL = 'http://live.bilibili.com/msg/send'
TV_URL = 'http://api.live.bilibili.com/SmallTV/join'
QUERY_RAFFLE_URL = 'http://api.live.bilibili.com/activity/v1/Raffle/check'
RAFFLE_URL = 'http://api.live.bilibili.com/activity/v1/Raffle/join'
QUERY_FREE_SILVER = 'http://api.live.bilibili.com/FreeSilver/getCurrentTask'
GET_FREE_SILVER = 'http://api.live.bilibili.com/FreeSilver/getAward'
CAPTCHA_URL = 'http://api.live.bilibili.com/freeSilver/getCaptcha?ts=%i'


class Sender(object):
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

    def _get(self, url, params=None):
        try:
            r = requests.get(url, params=params, cookies=self.cookies)
            return self._parseHttpResult(url, r)
        except:
            self.logger.error("HTTP GET REQ %s fail!" % url)

    def _post(self, url, params=None):
        try:
            r = requests.post(url, data=params, cookies=self.cookies)
            return self._parseHttpResult(url, r)
        except:
            self.logger.error("HTTP POST REQ %s fail!" % url)

    def _parseHttpResult(self, url, r):
        result = r.content
        raw = json.loads(result)
        self.logger.debug(raw)
        if raw['code'] != 0:
            self.logger.warn("API %s fail! MSG: %s" % (url, raw['msg']))
        return raw

    def checkLogin(self):
        r = self._get(LOGIN_CHECK_URL)
        if r and r['code'] == 'REPONSE_OK':
            print u'%s 登录成功' % r['data']['uname']
        else:
            print u'登录失败!'

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
            'id': tv_id,
            '_': int(time.time() * 100)
        }
        print u'参与 %s 小电视抽奖' % roomid
        self._get(TV_URL, params)

    def _joinRaffle(self, roomid, raffleId):
        params = {
            'roomid': roomid,
            'raffleId': raffleId
        }
        r = self._post(RAFFLE_URL, params)
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
                    print u'参与 %s 抽奖' % roomid
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
                        print u'获得奖品: %s 数量: %d' % (r['data']['gift_name'], r['data']['gift_num'])
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
            except:
                self.logger.warn('query free silver fail!')
            time.sleep(10)

    def downloadCaptcha(self, path='captcha.jpg'):
        t = int(time.time() * 1000)
        r = requests.get(CAPTCHA_URL % t, cookies=self.cookies)
        with open(path, 'w') as f:
            for chunk in r: f.write(chunk)
        return 'ok'

    def getFreeSilver(self, data):
        self.downloadCaptcha()
        captcha = ocr.recognize('captcha.jpg')

        params = {
            'time_start': data['time_start'],
            'end_time': data['time_end'],
            'captcha': captcha
        }
        r = self._get(GET_FREE_SILVER, params)
        if r['code'] == 0: self.logger.info('get %d silver coins' % r['awardSilver'])

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
            print u'%s 秒后再次获取瓜子' % int(r['data']['time_end'] - cur)
            return int(r['data']['time_end'] - cur)

    def startFreeSilverThread(self):
        print 'init ocr function...'
        if self.cookies:
            print 'checking free silver coins...'
            thread.start_new_thread(self.checkFreeSilver, ())


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
