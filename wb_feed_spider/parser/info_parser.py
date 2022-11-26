import logging
import sys

from ..user import User
from .parser import Parser
from .util import handle_html

logger = logging.getLogger("spider.info_parser")


class InfoParser(Parser):
    def __init__(self, cookie, user_id):
        self.cookie = cookie
        self.url = "https://weibo.cn/%s/info" % (user_id)
        self.selector = handle_html(self.cookie, self.url)

    def extract_user_info(self):
        """提取用户信息"""
        try:
            user = User()
            nickname = self.selector.xpath("//title/text()")[0]
            nickname = nickname[:-3]
            if nickname == "登录 - 新" or nickname == "新浪":
                logger.warning("cookie错误或已过期,请按照README中方法重新获取")
                sys.exit()
            user.nickname = nickname

            basic_info = self.selector.xpath("//div[@class='c'][3]/text()")
            zh_list = ["性别", "地区", "生日", "简介", "认证", "达人"]
            en_list = [
                "gender",
                "location",
                "birthday",
                "description",
                "verified_reason",
                "talent",
            ]
            for i in basic_info:
                if i.split(":", 1)[0] in zh_list:
                    setattr(
                        user,
                        en_list[zh_list.index(i.split(":", 1)[0])],
                        i.split(":", 1)[1].replace("\u3000", ""),
                    )

            experienced = self.selector.xpath("//div[@class='tip'][2]/text()")
            if experienced and experienced[0] == "学习经历":
                user.education = self.selector.xpath("//div[@class='c'][4]/text()")[0][
                    1:
                ].replace("\xa0", " ")
                if self.selector.xpath("//div[@class='tip'][3]/text()")[0] == "工作经历":
                    user.work = self.selector.xpath("//div[@class='c'][5]/text()")[0][
                        1:
                    ].replace("\xa0", " ")
            elif experienced and experienced[0] == "工作经历":
                user.work = self.selector.xpath("//div[@class='c'][4]/text()")[0][
                    1:
                ].replace("\xa0", " ")
            return user
        except Exception as e:
            logger.exception(e)
