#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# ------------------------------------------------------------
# File: base.py
# Created Date: 2020/7/12
# Created Time: 3:03
# Author: Hypdncy
# Author Mail: hypdncy@outlook.com
# Copyright (c) 2020 Hypdncy
# ------------------------------------------------------------
#                       .::::.
#                     .::::::::.
#                    :::::::::::
#                 ..:::::::::::'
#              '::::::::::::'
#                .::::::::::
#           '::::::::::::::..
#                ..::::::::::::.
#              ``::::::::::::::::
#               ::::``:::::::::'        .:::.
#              ::::'   ':::::'       .::::::::.
#            .::::'      ::::     .:::::::'::::.
#           .:::'       :::::  .:::::::::' ':::::.
#          .::'        :::::.:::::::::'      ':::::.
#         .::'         ::::::::::::::'         ``::::.
#     ...:::           ::::::::::::'              ``::.
#    ````':.          ':::::::::'                  ::::..
#                       '.:::::'                    ':'````..
# ------------------------------------------------------------
import asyncio
import logging
from abc import abstractmethod

from aiohttp import ClientResponse
from aiohttp.client import ClientSession, ClientTimeout

from cnf.const import translate_sem, translate_qps, translate_status, translate_auto_db, json_loops_error, vuln_db_file
from modle.common.loophole.loopholes import Loopholes
from modle.common.update.updb import UpdateDB


class TranBase(object):

    def __init__(self, LOOPHOLES: Loopholes):
        self.LOOPHOLES = LOOPHOLES
        self.timeout = ClientTimeout(total=30, connect=30, sock_connect=30, sock_read=30)
        self.tran_count = 0
        self.tran_number = 0
        self.update_db = UpdateDB(vuln_db_file)

    def _check_en2cn(self):
        for plugin_id, info in self.LOOPHOLES.items():
            if not info['name_cn']:
                raise

    async def _tran_http_with_sem(self, reqinfo, sem):
        async with sem:
            return await self._tran_http(reqinfo, sem)

    async def _tran_http(self, reqinfo, sem=None):
        await asyncio.sleep(1)
        async with ClientSession(timeout=self.timeout, headers=reqinfo.get("headers", {})) as session:
            try:
                async with session.request(method=reqinfo["method"], url=reqinfo["url"],
                                           **reqinfo["kwargs"]) as response:

                    data = await self._analysis_cn_resinfo(response, reqinfo["type_cn"])
                    self.tran_number += 1
                    print("------翻译漏洞进度：{0}/{1}".format(int(self.tran_number / 3) + 1, self.tran_count), end='\r')
                    return [reqinfo["plugin_id"], data]
            except Exception as e:
                logging.error("------翻译失败：plugin_id={}".format(int(reqinfo["plugin_id"])))
                logging.error(e)
                return [0, {}]

    async def _async_main(self):
        cn_resinfos = list()
        if not translate_status:
            logging.info("------翻译未开启")
            return cn_resinfos

        sem = None
        tran_func = self._tran_http
        en_reqinfos = self._make_en_reqinfos()
        logging.info("------翻译漏洞总数：{}".format(self.tran_count))

        if translate_sem > 0:
            tran_func = self._tran_http_with_sem
            sem = asyncio.Semaphore(translate_sem)
        if translate_qps > 0:
            reqtasks = [asyncio.create_task(tran_func(reqinfo, sem)) for reqinfo in en_reqinfos]
            for group in range(int(len(reqtasks) / translate_qps)):
                cn_resinfos.extend(await asyncio.gather(*reqtasks[group * translate_qps:(group + 1) * translate_qps]))
            cn_resinfos.extend(
                await asyncio.gather(*reqtasks[int((len(reqtasks) / translate_qps)) * translate_qps:]))
        else:
            reqtasks = [asyncio.create_task(tran_func(reqinfo)) for reqinfo in en_reqinfos]
            cn_resinfos = await asyncio.gather(*reqtasks)

        return cn_resinfos

    @abstractmethod
    def _make_en_reqinfos(self):
        pass

    @abstractmethod
    async def _analysis_cn_resinfo(self, response: ClientResponse, type_cn):
        pass

    def run(self):
        cn_resinfos = asyncio.run(self._async_main())
        for plugin_id, resinfo in cn_resinfos:
            # 翻译失败的直接略过
            if not (plugin_id and resinfo):
                continue
            for type_cn, cn_text in resinfo.items():
                self.LOOPHOLES[plugin_id][type_cn] = cn_text
        self._check_en2cn()
        self.LOOPHOLES.dump_loops()
        if translate_auto_db:
            self.update_db.update_db_from_file(json_loops_error)
        logging.info("------翻译完成")
