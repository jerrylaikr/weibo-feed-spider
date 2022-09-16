from datetime import datetime, timedelta
import logging
import re
import sys
from weibo_spider import datetime_util
from weibo_spider.parser.mblog_picAll_parser import MblogPicAllParser
from weibo_spider.weibo import Weibo
from weibo_spider.parser.parser import Parser
from weibo_spider.parser.util import handle_html, handle_garbled, to_video_download_url
from weibo_spider.parser.comment_parser import CommentParser

logger = logging.getLogger("spider.page_parser")


class PageParser(Parser):
    def __init__(self, cookie, filter, since_time) -> None:
        self.cookie = cookie
        self.since_time = since_time
        self.url = "https://weibo.cn/"
        self.selector = ""
        self.to_continue = True

        is_exist = ""
        for _ in range(3):
            self.selector = handle_html(self.cookie, self.url)
            info = self.selector.xpath("//div[@class='c']")
            if info is None or len(info) == 0:
                continue
            is_exist = info[0].xpath("div/span[@class='ctt']")
            if is_exist:
                self.empty_count = 0
                break
        if not is_exist:
            self.empty_count += 1
        if self.empty_count > 2:
            self.to_continue = False
            self.empty_count = 0
        self.filter = filter

    def get_one_page(self, weibo_id_list: list):
        """Get everything on the first page of my feed"""
        try:
            info = self.selector.xpath("//div[@class='c']")
            is_exist = info[0].xpath("div/span[@class='ctt']")
            weibos = []
            if is_exist:
                for i in range(len(info) - 1):
                    weibo = self.get_one_weibo(info[i])
                    if weibo:
                        if weibo.id in weibo_id_list:
                            continue
                        publish_time = datetime_util.str_to_time(weibo.publish_time)

                        # NOTE: debug begins
                        # TODO: change this to debug level instead of info
                        logger.info("#" * 120)
                        logger.info("user_id = " + weibo.user_id)
                        logger.info(weibo.content)
                        logger.info(
                            f'publish_time = {publish_time.strftime("%Y-%m-%d %H:%M:%S")} '
                            + f'since_time = {self.since_time.strftime("%Y-%m-%d %H:%M:%S")}'
                        )
                        logger.info("#" * 120)
                        # NOTE: debug ends

                        if publish_time < self.since_time:
                            return weibos, weibo_id_list, False
                        logger.info(weibo)
                        logger.info("-" * 100)
                        weibos.append(weibo)
                        weibo_id_list.append(weibo.id)

            return weibos, weibo_id_list, self.to_continue

        except Exception as e:
            logger.exception(e)

    def is_original(self, info):
        """判断微博是否为原创微博"""
        is_original = info.xpath("div/span[@class='cmt']")
        if len(is_original) > 3:
            return False
        else:
            return True

    def get_original_weibo(self, info, weibo_id):
        """获取原创微博"""
        try:
            weibo_content = handle_garbled(info)
            weibo_content = weibo_content[: weibo_content.rfind("赞")]
            a_text = info.xpath("div//a/text()")
            if "全文" in a_text:
                wb_content = CommentParser(self.cookie, weibo_id).get_long_weibo()
                if wb_content:
                    weibo_content = wb_content
            return weibo_content
        except Exception as e:
            logger.exception(e)

    def get_retweet(self, info, weibo_id):
        """获取转发微博"""
        try:
            weibo_content = handle_garbled(info)
            weibo_content = weibo_content[
                weibo_content.find(":") + 1 : weibo_content.rfind("赞")
            ]
            weibo_content = weibo_content[: weibo_content.rfind("赞")]
            a_text = info.xpath("div//a/text()")
            if "全文" in a_text:
                wb_content = CommentParser(self.cookie, weibo_id).get_long_retweet()
                if wb_content:
                    weibo_content = wb_content
            retweet_reason = handle_garbled(info.xpath("div")[-1])
            retweet_reason = retweet_reason[: retweet_reason.rindex("赞")]
            original_user = info.xpath("div/span[@class='cmt']/a/text()")
            if original_user:
                original_user = original_user[0]
                weibo_content = (
                    retweet_reason
                    + "\n"
                    + "原始用户: "
                    + original_user
                    + "\n"
                    + "转发内容: "
                    + weibo_content
                )
            else:
                weibo_content = retweet_reason + "\n" + "转发内容: " + weibo_content
            return weibo_content
        except Exception as e:
            logger.exception(e)

    def get_weibo_content(self, info, is_original):
        """获取微博内容"""
        try:
            weibo_id = info.xpath("@id")[0][2:]
            if is_original:
                weibo_content = self.get_original_weibo(info, weibo_id)
            else:
                weibo_content = self.get_retweet(info, weibo_id)
            return weibo_content
        except Exception as e:
            logger.exception(e)

    def get_article_url(self, info):
        """获取微博头条文章的url"""
        article_url = ""
        text = handle_garbled(info)
        if text.startswith("发布了头条文章"):
            url = info.xpath(".//a/@href")
            if url and url[0].startswith("https://weibo.cn/sinaurl"):
                article_url = url[0]
        return article_url

    def get_publish_place(self, info):
        """获取微博发布位置"""
        try:
            div_first = info.xpath("div")[0]
            a_list = div_first.xpath("a")
            publish_place = "无"
            for a in a_list:
                if (
                    "place.weibo.com" in a.xpath("@href")[0]
                    and a.xpath("text()")[0] == "显示地图"
                ):
                    weibo_a = div_first.xpath("span[@class='ctt']/a")
                    if len(weibo_a) >= 1:
                        publish_place = weibo_a[-1]
                        if (
                            "视频"
                            == div_first.xpath("span[@class='ctt']/a/text()")[-1][-2:]
                        ):
                            if len(weibo_a) >= 2:
                                publish_place = weibo_a[-2]
                            else:
                                publish_place = "无"
                        publish_place = handle_garbled(publish_place)
                        break
            return publish_place
        except Exception as e:
            logger.exception(e)

    def get_publish_time(self, info):
        """获取微博发布时间"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = handle_garbled(str_time[0])
            publish_time = str_time.split("来自")[0]
            if "刚刚" in publish_time:
                publish_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            elif "分钟" in publish_time:
                minute = publish_time[: publish_time.find("分钟")]
                minute = timedelta(minutes=int(minute))
                publish_time = (datetime.now() - minute).strftime("%Y-%m-%d %H:%M")
            elif "今天" in publish_time:
                today = datetime.now().strftime("%Y-%m-%d")
                time = publish_time[3:]
                publish_time = today + " " + time
                if len(publish_time) > 16:
                    publish_time = publish_time[:16]
            elif "月" in publish_time:
                year = datetime.now().strftime("%Y")
                month = publish_time[0:2]
                day = publish_time[3:5]
                time = publish_time[7:12]
                publish_time = year + "-" + month + "-" + day + " " + time
            else:
                publish_time = publish_time[:16]
            return publish_time
        except Exception as e:
            logger.exception(e)

    def get_publish_tool(self, info):
        """获取微博发布工具"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = handle_garbled(str_time[0])
            if len(str_time.split("来自")) > 1:
                publish_tool = str_time.split("来自")[1]
            else:
                publish_tool = "无"
            return publish_tool
        except Exception as e:
            logger.exception(e)

    def get_weibo_footer(self, info):
        """获取微博点赞数、转发数、评论数"""
        try:
            footer = {}
            pattern = r"\d+"
            str_footer = info.xpath("div")[-1]
            str_footer = handle_garbled(str_footer)
            str_footer = str_footer[str_footer.rfind("赞") :]
            weibo_footer = re.findall(pattern, str_footer, re.M)

            up_num = int(weibo_footer[0])
            footer["up_num"] = up_num

            retweet_num = int(weibo_footer[1])
            footer["retweet_num"] = retweet_num

            comment_num = int(weibo_footer[2])
            footer["comment_num"] = comment_num
            return footer
        except Exception as e:
            logger.exception(e)

    def get_picture_urls(self, info, is_original):
        """获取微博原始图片url"""
        try:
            weibo_id = info.xpath("@id")[0][2:]
            picture_urls = {}
            if is_original:
                original_pictures = self.extract_picture_urls(info, weibo_id)
                picture_urls["original_pictures"] = original_pictures
                if not self.filter:
                    picture_urls["retweet_pictures"] = "无"
            else:
                retweet_url = info.xpath("div/a[@class='cc']/@href")[0]
                retweet_id = retweet_url.split("/")[-1].split("?")[0]
                retweet_pictures = self.extract_picture_urls(info, retweet_id)
                picture_urls["retweet_pictures"] = retweet_pictures
                a_list = info.xpath("div[last()]/a/@href")
                original_picture = "无"
                for a in a_list:
                    if a.endswith((".gif", ".jpeg", ".jpg", ".png")):
                        original_picture = a
                        break
                picture_urls["original_pictures"] = original_picture
            return picture_urls
        except Exception as e:
            logger.exception(e)

    def get_video_url(self, info):
        """获取微博视频url"""
        video_url = "无"

        weibo_id = info.xpath("@id")[0][2:]
        try:
            video_page_url = ""
            a_text = info.xpath("./div[1]//a/text()")
            if "全文" in a_text:
                video_page_url = CommentParser(
                    self.cookie, weibo_id
                ).get_video_page_url()
            else:
                # 来自微博视频号的格式与普通格式不一致，不加 span 层级
                a_list = info.xpath("./div[1]//a")
                for a in a_list:
                    if "m.weibo.cn/s/video/show?object_id=" in a.xpath("@href")[0]:
                        video_page_url = a.xpath("@href")[0]
                        break

            if video_page_url != "":
                video_url = to_video_download_url(self.cookie, video_page_url)
        except Exception as e:
            logger.exception(e)

        return video_url

    def get_weibo_user_id(self, info):
        """Get the id of the user who posted this wb"""
        try:
            user_id = info.xpath("./div/a[@class='nk']/@href")[0].split("/")[-1]
        except Exception as e:
            logger.exception(e)

        return user_id

    def get_one_weibo(self, info) -> Weibo:
        """获取一条微博的全部信息"""
        try:
            weibo = Weibo()
            is_original = self.is_original(info)
            weibo.original = is_original  # 是否原创微博
            if (not self.filter) or is_original:
                weibo.id = info.xpath("@id")[0][2:]
                weibo.user_id = self.get_weibo_user_id(info)
                weibo.content = self.get_weibo_content(info, is_original)  # 微博内容
                weibo.article_url = self.get_article_url(info)  # 头条文章url
                picture_urls = self.get_picture_urls(info, is_original)
                weibo.original_pictures = picture_urls["original_pictures"]  # 原创图片url
                if not self.filter:
                    weibo.retweet_pictures = picture_urls["retweet_pictures"]  # 转发图片url
                weibo.video_url = self.get_video_url(info)  # 微博视频url
                weibo.publish_place = self.get_publish_place(info)  # 微博发布位置
                weibo.publish_time = self.get_publish_time(info)  # 微博发布时间
                weibo.publish_tool = self.get_publish_tool(info)  # 微博发布工具
                footer = self.get_weibo_footer(info)
                weibo.up_num = footer["up_num"]  # 微博点赞数
                weibo.retweet_num = footer["retweet_num"]  # 转发数
                weibo.comment_num = footer["comment_num"]  # 评论数
            else:
                weibo = None
                logger.info("正在过滤转发微博")
            return weibo
        except Exception as e:
            logger.exception(e)

    def extract_picture_urls(self, info, weibo_id):
        """提取微博原始图片url"""
        try:
            a_list = info.xpath("div/a/@href")
            first_pic = "https://weibo.cn/mblog/pic/" + weibo_id
            all_pic = "https://weibo.cn/mblog/picAll/" + weibo_id
            picture_urls = "无"
            if first_pic in "".join(a_list):
                if all_pic in "".join(a_list):
                    preview_picture_list = MblogPicAllParser(
                        self.cookie, weibo_id
                    ).extract_preview_picture_list()
                    picture_list = [
                        p.replace("/thumb180/", "/large/") for p in preview_picture_list
                    ]
                    picture_urls = ",".join(picture_list)
                else:
                    if info.xpath(".//img/@src"):
                        for link in info.xpath("div/a"):
                            if len(link.xpath("@href")) > 0:
                                if first_pic in link.xpath("@href")[0]:
                                    if len(link.xpath("img/@src")) > 0:
                                        preview_picture = link.xpath("img/@src")[0]
                                        picture_urls = preview_picture.replace(
                                            "/wap180/", "/large/"
                                        )
                                        break
                    else:
                        logger.warning(
                            '爬虫微博可能被设置成了"不显示图片"，请前往'
                            '"https://weibo.cn/account/customize/pic"，修改为"显示"'
                        )
                        sys.exit()
            return picture_urls
        except Exception as e:
            logger.exception(e)
            return "无"
