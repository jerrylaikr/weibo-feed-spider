#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from datetime import datetime
import json
import logging
import logging.config
import os
import shutil
import sys
import time
from typing import Generator

from tqdm import tqdm
from weibo_spider.parser import AlbumParser, IndexParser, PhotoParser
from weibo_spider.downloader import AvatarPictureDownloader
from weibo_spider.user import User
from weibo_spider.weibo import Weibo

from .parser import PageParser
from . import config_util

logging_path = os.path.split(os.path.realpath(__file__))[0] + os.sep + "logging.conf"
logging.config.fileConfig(logging_path)
logger = logging.getLogger("spider")


class Spider:
    def __init__(self, config: dict) -> None:
        """Spider类初始化"""
        self.cookie = config["cookie"]  # user cookie
        self.filter = config["filter"]  # 取值范围为0、1,程序默认值为0,代表要爬取用户的全部微博,1代表只爬取用户的原创微博

        ## get interval between refreshes (in seconds)
        self.refresh_interval = config["refresh_interval"]

        ## get DB configs
        # self.mysql_config = config.get('mysql_config')
        # self.sqlite_config = config.get('sqlite_config')
        # self.kafka_config = config.get('kafka_config')
        self.mongo_config = config.get("mongo_config")

        ## get writer/downloader config
        self.write_mode = config[
            "write_mode"
        ]  # 结果信息保存类型，为list形式，可包含txt、csv、json、mongo和mysql五种类型
        self.pic_download = config["pic_download"]  # 取值范围为0、1,程序默认值为0,代表不下载微博原始图片,1代表下载
        self.video_download = config[
            "video_download"
        ]  # 取值范围为0、1,程序默认为0,代表不下载微博视频,1代表下载
        self.file_download_timeout = config.get(
            "file_download_timeout", [5, 5, 10]
        )  # 控制文件下载“超时”时的操作，值是list形式，包含三个数字，依次分别是最大超时重试次数、最大连接时间和最大读取时间
        self.result_dir_name = config.get(
            "result_dir_name", 0
        )  # 结果目录名，取值为0或1，决定结果文件存储在用户昵称文件夹里还是用户id文件夹里

        self.writers = []
        if "csv" in self.write_mode:
            from weibo_spider.writer import CsvWriter

            self.writers.append(CsvWriter(self._get_filepath("csv"), self.filter))
        if "txt" in self.write_mode:
            from weibo_spider.writer import TxtWriter

            self.writers.append(TxtWriter(self._get_filepath("txt"), self.filter))
        if "json" in self.write_mode:
            from weibo_spider.writer import JsonWriter

            self.writers.append(JsonWriter(self._get_filepath("json")))
        if "mongo" in self.write_mode:
            from weibo_spider.writer import MongoWriter

            self.writers.append(MongoWriter(self.mongo_config))
        # if "mysql" in self.write_mode:
        #     from .writer import MySqlWriter

        #     self.writers.append(MySqlWriter(self.mysql_config))
        # if "sqlite" in self.write_mode:
        #     from .writer import SqliteWriter

        #     self.writers.append(SqliteWriter(self.sqlite_config))
        # if "kafka" in self.write_mode:
        #     from .writer import KafkaWriter

        #     self.writers.append(KafkaWriter(self.kafka_config))

        self.downloaders = []
        if self.pic_download == 1:
            from weibo_spider.downloader import (
                OriginPictureDownloader,
                RetweetPictureDownloader,
            )

            self.downloaders.append(
                OriginPictureDownloader(
                    self._get_filepath("img"), self.file_download_timeout
                )
            )
        if self.pic_download and not self.filter:
            self.downloaders.append(
                RetweetPictureDownloader(
                    self._get_filepath("img"), self.file_download_timeout
                )
            )
        if self.video_download == 1:
            from weibo_spider.downloader import VideoDownloader

            self.downloaders.append(
                VideoDownloader(self._get_filepath("video"), self.file_download_timeout)
            )

        ## initialize starting time
        self.since_time = datetime.now()

        ## initialize statistical info
        self.got_num = 0
        self.weibo_id_list = []
        self.user_id_set = set()

    def write_weibo(self, weibos: list[Weibo]):
        """Write weibos to file and/or database"""
        for writer in self.writers:
            writer.write_weibo(weibos)
        for downloader in self.downloaders:
            downloader.download_files(weibos)

    def write_user(self, user):
        """Write user info to file and/or database"""
        for writer in self.writers:
            writer.write_user(user)

    def get_user_info(self, user_uri) -> User:
        """获取用户信息"""
        return IndexParser(self.cookie, user_uri).get_user()

    def download_user_avatar(self, user_uri):
        """下载用户头像"""
        avatar_album_url = PhotoParser(self.cookie, user_uri).extract_avatar_album_url()
        pic_urls = AlbumParser(self.cookie, avatar_album_url).extract_pic_urls()
        AvatarPictureDownloader(
            self._get_filepath("img"), self.file_download_timeout
        ).handle_download(pic_urls)

    def get_weibo_info(self) -> Generator[list[Weibo], None, None]:
        """Parse web request and get weibo info"""
        ## TODO: add support to parse multiple pages
        try:
            weibos, self.weibo_id_list, to_continue = PageParser(
                self.cookie, self.filter, self.since_time
            ).get_one_page(self.weibo_id_list)
            if weibos:
                yield weibos
            # if not to_continue:
            #     break

        except Exception as e:
            logger.exception(e)

    def sleep(self):
        """Sleep till next refresh"""
        self.since_time = datetime.now()
        logger.info(f"Reset since_time to {self.since_time}")
        logger.info(f"Sleeping for {self.refresh_interval} seconds...")
        for _ in tqdm(range(self.refresh_interval)):
            time.sleep(1)

    def get_feed(self):
        """Start fetching weibos posted aft last refresh from my feed"""
        ## Adapted based on combination of Spider.get_one_user() and Spider.start()
        try:
            logger.info(
                "Start fetching weibos posted after: "
                + self.since_time.strftime("%Y-%m-%d %H:%M")
            )

            self.got_num = 0  # reset the number of wbs fetched in this refresh
            self.weibo_id_list = []  # NOTE: I have no clue what's the purpose of this

            for weibos in self.get_weibo_info():
                for wb in tqdm(weibos):
                    if wb.user_id not in self.user_id_set:
                        self.write_user(self.get_user_info(wb.user_id))
                        self.user_id_set.add(wb.user_id)
                    self.write_weibo([wb])
                self.got_num += len(weibos)

            if not self.filter:
                logger.info("共爬取" + str(self.got_num) + "条微博")
            else:
                logger.info("共爬取" + str(self.got_num) + "条原创微博")
            logger.info("信息抓取完毕")
            logger.info("*" * 100)

        except Exception as e:
            logger.exception(e)


def _get_config():
    """Get config from config.json"""
    src = os.path.split(os.path.realpath(__file__))[0] + os.sep + "config_sample.json"
    config_path = os.getcwd() + os.sep + "config.json"

    if not os.path.isfile(config_path):
        shutil.copy(src, config_path)
        logger.info(f"请先配置当前目录({os.getcwd()})下的config.json文件")
        sys.exit()
    try:
        with open(config_path) as f:
            config = json.loads(f.read())
            return config
    except ValueError:
        logger.error("config.json 格式不正确")
        sys.exit()


def main():
    try:
        config = _get_config()
        config_util.validate_config(config)
        wb = Spider(config)

        while True:
            wb.sleep()  # update time_since and sleep for refresh interval
            wb.get_feed()  # start running

    except Exception as e:
        logger.exception(e)


if __name__ == "__main__":
    main()
