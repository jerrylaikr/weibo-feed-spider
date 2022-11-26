import copy
import logging
import sys

from .writer import Writer
from ..weibo import Weibo
from ..user import User

logger = logging.getLogger("spider.mongo_writer")


class MongoWriter(Writer):
    def __init__(self, mongo_config: dict):
        self.mongo_config = mongo_config
        self.connection_string = mongo_config["connection_string"]
        self.dba_name = mongo_config.get("dba_name", None)
        self.dba_password = mongo_config.get("dba_password", None)

    def _info_to_mongodb(self, collection: str, info_list: list[dict]):
        """将爬取的信息写入MongoDB数据库"""
        try:
            import pymongo
        except ImportError:
            logger.warning("系统中可能没有安装pymongo库，请先运行 pip install pymongo ，再运行程序")
            sys.exit()
        try:
            from pymongo import MongoClient

            client = MongoClient(self.connection_string)
            if self.dba_name or self.dba_password:
                # authenticate() 在PyMongo3.6版本就已弃用，这一段可能需要后续跟进
                client.admin.authenticate(
                    self.dba_name, self.dba_password, mechanism="SCRAM-SHA-1"
                )

            db = client["weibo"]
            collection = db[collection]
            new_info_list = copy.deepcopy(info_list)
            for info in new_info_list:
                if not collection.find_one({"id": info["id"]}):
                    collection.insert_one(info)
                else:
                    collection.update_one({"id": info["id"]}, {"$set": info})
        except pymongo.errors.ServerSelectionTimeoutError:
            logger.warning("系统中可能没有安装或启动MongoDB数据库，请先根据系统环境安装或启动MongoDB，再运行程序")
            sys.exit()

    def write_weibo(self, weibos: list[Weibo]):
        """将爬取的微博信息写入MongoDB数据库"""
        weibo_list = []
        for w in weibos:
            weibo_list.append(w.__dict__)
        self._info_to_mongodb("weibo", weibo_list)
        logger.info("%d条微博写入MongoDB数据库完毕", len(weibos))

    def write_user(self, user: User):
        """将爬取的用户信息写入MongoDB数据库"""
        user_list = [user.__dict__]
        self._info_to_mongodb("user", user_list)
        logger.info("%s信息写入MongoDB数据库完毕", user.nickname)
