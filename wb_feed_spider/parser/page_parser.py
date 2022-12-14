from datetime import datetime, timedelta
import logging
import re
import sys
from .. import datetime_util
from ..weibo import Weibo
from .comment_parser import CommentParser
from .mblog_picAll_parser import MblogPicAllParser
from .parser import Parser
from .util import handle_html, handle_garbled, to_video_download_url

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
                        logger.info("~" * 100)
                        logger.info("user_id = " + weibo.user_id)
                        logger.info(weibo.id)
                        logger.info(
                            f'publish_time = {publish_time.strftime("%Y-%m-%d %H:%M:%S")} '
                            + f'since_time = {self.since_time.strftime("%Y-%m-%d %H:%M:%S")}'
                        )
                        logger.info("~" * 100)
                        # NOTE: debug ends

                        if publish_time < self.since_time - timedelta(minutes=1):
                            logger.info(
                                "Publish_time earlier than since_time, returning..."
                            )
                            logger.info(f"fetched {len(weibos)} wbs")
                            return weibos, weibo_id_list, False
                        logger.info("\n" + str(weibo))
                        logger.info("-" * 100)
                        weibos.append(weibo)
                        weibo_id_list.append(weibo.id)

            logger.info(f"fetched {len(weibos)} wbs")
            return weibos, weibo_id_list, self.to_continue

        except Exception as e:
            logger.exception(e)

    def is_original(self, info):
        """?????????????????????????????????"""
        is_original = info.xpath("div/span[@class='cmt']")
        if len(is_original) > 3:
            return False
        else:
            return True

    def get_original_weibo(self, info, weibo_id):
        """??????????????????
        Feed???????????????????????????
            <USER>
            :<CONTENT>
            ???[0] ??????[0] ??????[0] ?????? ...
        """
        try:
            weibo_content = handle_garbled(info)

            # ?????? ???<USER>:??? ??? ??????[0] ??????[0] ??????[0] ?????? ...??? ??????
            weibo_content = weibo_content[
                weibo_content.find(":") + 1 : weibo_content.rfind("???")
            ]

            a_text = info.xpath("div//a/text()")
            if "??????" in a_text:
                wb_content = CommentParser(self.cookie, weibo_id).get_long_weibo()
                if wb_content:
                    weibo_content = wb_content
            return weibo_content
        except Exception as e:
            logger.exception(e)

    def get_retweet(self, info, weibo_id):
        """??????????????????
        Feed???????????????????????????
            <USER>?????????<USER>?????????:
            <ORIGINAL_CONTENT>
            ???[0] ????????????[0] ????????????[0]
            ????????????:
            <RETWEET_CONTENT>
            ???[0] ??????[0] ??????[0] ?????? ...
        """
        try:
            weibo_content = handle_garbled(info)

            # ?????? ???<USER>?????????<USER>?????????:??? ??? ??????[0] ??????[0] ??????[0] ?????? ...??? ??????
            weibo_content = weibo_content[
                weibo_content.find(":") + 1 : weibo_content.rfind("???")
            ]

            # ?????? ??????[0] ????????????[0] ????????????[0] ????????????:??? ??????????????????
            weibo_content = weibo_content[: weibo_content.rfind("???")]

            a_text = info.xpath("div//a/text()")
            if "??????" in a_text:
                wb_content = CommentParser(self.cookie, weibo_id).get_long_retweet()
                if wb_content:
                    weibo_content = wb_content
            retweet_reason = handle_garbled(info.xpath("div")[-1])
            retweet_reason = retweet_reason[: retweet_reason.rindex("???")]
            original_user = info.xpath("div/span[@class='cmt']/a/text()")
            if original_user:
                original_user = original_user[0]
                weibo_content = (
                    retweet_reason
                    + "\n"
                    + "????????????: "
                    + original_user
                    + "\n"
                    + "????????????: "
                    + weibo_content
                )
            else:
                weibo_content = retweet_reason + "\n" + "????????????: " + weibo_content
            return weibo_content
        except Exception as e:
            logger.exception(e)

    def get_weibo_content(self, info, is_original):
        """??????????????????"""
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
        """???????????????????????????url"""
        article_url = ""
        text = handle_garbled(info)
        if text.startswith("?????????????????????"):
            url = info.xpath(".//a/@href")
            if url and url[0].startswith("https://weibo.cn/sinaurl"):
                article_url = url[0]
        return article_url

    def get_publish_place(self, info):
        """????????????????????????"""
        try:
            div_first = info.xpath("div")[0]
            a_list = div_first.xpath("a")
            publish_place = "???"
            for a in a_list:
                if (
                    "place.weibo.com" in a.xpath("@href")[0]
                    and a.xpath("text()")[0] == "????????????"
                ):
                    weibo_a = div_first.xpath("span[@class='ctt']/a")
                    if len(weibo_a) >= 1:
                        publish_place = weibo_a[-1]
                        if (
                            "??????"
                            == div_first.xpath("span[@class='ctt']/a/text()")[-1][-2:]
                        ):
                            if len(weibo_a) >= 2:
                                publish_place = weibo_a[-2]
                            else:
                                publish_place = "???"
                        publish_place = handle_garbled(publish_place)
                        break
            return publish_place
        except Exception as e:
            logger.exception(e)

    def get_publish_time(self, info):
        """????????????????????????"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = handle_garbled(str_time[0])
            publish_time = str_time.split("??????")[0]
            if "??????" in publish_time:
                publish_time = datetime.now().strftime("%Y-%m-%d %H:%M")
            elif "??????" in publish_time:
                minute = publish_time[: publish_time.find("??????")]
                minute = timedelta(minutes=int(minute))
                publish_time = (datetime.now() - minute).strftime("%Y-%m-%d %H:%M")
            elif "??????" in publish_time:
                today = datetime.now().strftime("%Y-%m-%d")
                time = publish_time[3:]
                publish_time = today + " " + time
                if len(publish_time) > 16:
                    publish_time = publish_time[:16]
            elif "???" in publish_time:
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
        """????????????????????????"""
        try:
            str_time = info.xpath("div/span[@class='ct']")
            str_time = handle_garbled(str_time[0])
            if len(str_time.split("??????")) > 1:
                publish_tool = str_time.split("??????")[1]
            else:
                publish_tool = "???"
            return publish_tool
        except Exception as e:
            logger.exception(e)

    def get_weibo_footer(self, info):
        """?????????????????????????????????????????????"""
        try:
            footer = {}
            pattern = r"\d+"
            str_footer = info.xpath("div")[-1]
            str_footer = handle_garbled(str_footer)
            str_footer = str_footer[str_footer.rfind("???") :]
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
        """????????????????????????url"""
        try:
            weibo_id = info.xpath("@id")[0][2:]
            picture_urls = {}
            if is_original:
                original_pictures = self.extract_picture_urls(info, weibo_id)
                picture_urls["original_pictures"] = original_pictures
                if not self.filter:
                    picture_urls["retweet_pictures"] = "???"
            else:
                retweet_url = info.xpath("div/a[@class='cc']/@href")[0]
                retweet_id = retweet_url.split("/")[-1].split("?")[0]
                retweet_pictures = self.extract_picture_urls(info, retweet_id)
                picture_urls["retweet_pictures"] = retweet_pictures
                a_list = info.xpath("div[last()]/a/@href")
                original_picture = "???"
                for a in a_list:
                    if a.endswith((".gif", ".jpeg", ".jpg", ".png")):
                        original_picture = a
                        break
                picture_urls["original_pictures"] = original_picture
            return picture_urls
        except Exception as e:
            logger.exception(e)

    def get_video_url(self, info):
        """??????????????????url"""
        video_url = "???"

        weibo_id = info.xpath("@id")[0][2:]
        try:
            video_page_url = ""
            a_text = info.xpath("./div[1]//a/text()")
            if "??????" in a_text:
                video_page_url = CommentParser(
                    self.cookie, weibo_id
                ).get_video_page_url()
            else:
                # ??????????????????????????????????????????????????????????????? span ??????
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
        """?????????????????????????????????"""
        try:
            weibo = Weibo()
            is_original = self.is_original(info)
            weibo.original = is_original  # ??????????????????
            if (not self.filter) or is_original:
                weibo.id = info.xpath("@id")[0][2:]
                weibo.user_id = self.get_weibo_user_id(info)
                weibo.content = self.get_weibo_content(info, is_original)  # ????????????
                weibo.article_url = self.get_article_url(info)  # ????????????url
                picture_urls = self.get_picture_urls(info, is_original)
                weibo.original_pictures = picture_urls["original_pictures"]  # ????????????url
                if not self.filter:
                    weibo.retweet_pictures = picture_urls["retweet_pictures"]  # ????????????url
                weibo.video_url = self.get_video_url(info)  # ????????????url
                weibo.publish_place = self.get_publish_place(info)  # ??????????????????
                weibo.publish_time = self.get_publish_time(info)  # ??????????????????
                weibo.publish_tool = self.get_publish_tool(info)  # ??????????????????
                footer = self.get_weibo_footer(info)
                weibo.up_num = footer["up_num"]  # ???????????????
                weibo.retweet_num = footer["retweet_num"]  # ?????????
                weibo.comment_num = footer["comment_num"]  # ?????????
            else:
                weibo = None
                logger.info("????????????????????????")
            return weibo
        except Exception as e:
            logger.exception(e)

    def extract_picture_urls(self, info, weibo_id):
        """????????????????????????url"""
        try:
            a_list = info.xpath("div/a/@href")
            first_pic = "https://weibo.cn/mblog/pic/" + weibo_id
            all_pic = "https://weibo.cn/mblog/picAll/" + weibo_id
            picture_urls = "???"
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
                            '?????????????????????????????????"???????????????"????????????'
                            '"https://weibo.cn/account/customize/pic"????????????"??????"'
                        )
                        sys.exit()
            return picture_urls
        except Exception as e:
            logger.exception(e)
            return "???"
