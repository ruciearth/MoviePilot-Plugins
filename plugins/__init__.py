#!/usr/bin/env python3
# -*- coding:utf-8 -*-
import logging
import json
import urllib.request
from datetime import datetime
from moviebotapi.core.plugin import _PluginBase
from moviebotapi import MovieBotServer
from moviebotapi.core.background import ScheduleJob
from moviebotapi.core.message import MessageChannel

logger = logging.getLogger(__name__)

class HotMediaDaily(_PluginBase):
    # 插件元数据
    plugin_id = "HotMediaDaily"
    plugin_name = "每日热播推送"
    plugin_version = "2.2"
    plugin_description = "每日定时推送国内热播影视资源"
    plugin_author = "MovieBot"
    plugin_icon = "https://img.icons8.com/color/48/tv-show.png"
    plugin_default_enable = True
    plugin_params = {
        "push_time": {
            "name": "推送时间",
            "type": "str",
            "default": "10:00",
            "description": "每日推送时间 (HH:MM)"
        },
        "max_items": {
            "name": "最大条目数",
            "type": "int",
            "default": 5,
            "description": "每种类型最多推送条目"
        }
    }

    def __init__(self, mb: MovieBotServer):
        super().__init__(mb)
        self.config = self.get_config()
        self.schedule_job = None
        
    def load(self):
        logger.info("每日热播推送插件开始加载")
        
        # 解析推送时间
        push_time = self.config.get('push_time', '10:00')
        try:
            hour, minute = map(int, push_time.split(':'))
        except:
            hour, minute = 10, 0
        
        # 添加每日任务
        self.schedule_job = ScheduleJob(
            job_id=f"{self.plugin_id}_push_job",
            func=self.push_hot_media,
            trigger="cron",
            hour=hour,
            minute=minute
        )
        
        try:
            self.mb.schedule.add_job(self.schedule_job)
            logger.info(f"定时任务已添加: 每天 {hour}:{minute:02d} 执行")
        except Exception as e:
            logger.error(f"添加定时任务失败: {str(e)}")
        
        logger.info("插件加载完成")

    def unload(self):
        logger.info("开始卸载插件")
        
        if self.schedule_job:
            try:
                self.mb.schedule.remove_job(self.schedule_job.job_id)
                logger.info(f"定时任务 {self.schedule_job.job_id} 已移除")
            except Exception as e:
                logger.error(f"移除定时任务失败: {str(e)}")
        
        logger.info("插件已卸载")

    def get_config(self):
        try:
            config = self.read_default_config()
            if config:
                return config
        except Exception as e:
            logger.error(f"读取配置失败: {str(e)}")
        
        return {
            "push_time": "10:00",
            "max_items": 5
        }

    def push_hot_media(self):
        """获取并推送热播影视资源"""
        try:
            logger.info("开始执行热播资源推送任务")
            max_items = self.config.get('max_items', 5)
            
            # 获取热播数据
            movies = self.get_douban_hot("movie", max_items)
            tvs = self.get_douban_hot("tv", max_items)
            
            all_items = movies + tvs
            logger.info(f"获取到 {len(all_items)} 条热播资源")
            
            if not all_items:
                logger.warning("未获取到热播资源")
                return
                
            # 发送通知
            self.send_notification(all_items)
                
            logger.info("推送任务完成")
        except Exception as e:
            logger.error(f"推送失败: {str(e)}", exc_info=True)

    def send_notification(self, items):
        """发送通知"""
        movie_count = sum(1 for item in items if item['media_type'] == "movie")
        tv_count = sum(1 for item in items if item['media_type'] == "tv")
        
        text = f"🎬 今日热播推荐 ({datetime.now().strftime('%Y-%m-%d')})\n\n"
        text += f"🔥 热门电影: {movie_count}部\n"
        text += f"📺 热门剧集: {tv_count}部\n\n"
        
        # 添加详细信息
        for i, item in enumerate(items, 1):
            media_type = "电影" if item['media_type'] == "movie" else "剧集"
            text += f"{i}. [{media_type}] {item['title']} ({item.get('year', '')})"
            
            if item.get('rating'):
                text += f" ⭐{item['rating']}"
            
            if item.get('douban_id'):
                text += f"\n豆瓣: https://movie.douban.com/subject/{item['douban_id']}/"
            
            text += "\n\n"
        
        # 发送通知
        self.mb.notify.send_message(
            channel=MessageChannel.Plugin,
            title="今日热播资源推荐",
            text=text
        )

    def get_douban_hot(self, media_type, count=5):
        """从豆瓣获取热播影视数据"""
        api_endpoints = {
            "movie": "https://m.douban.com/rexxar/api/v2/subject_collection/movie_showing/items",
            "tv": "https://m.douban.com/rexxar/api/v2/subject_collection/tv_hot/items"
        }
        
        if media_type not in api_endpoints:
            return []
        
        url = api_endpoints[media_type]
        params = f"start=0&count={count}"
        full_url = f"{url}?{params}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://movie.douban.com/",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        try:
            # 创建请求对象
            req = urllib.request.Request(full_url, headers=headers)
            
            # 发送请求
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            items = data.get('subject_collection_items', [])[:count]
            
            result = []
            for item in items:
                result.append({
                    'title': item.get('title', ''),
                    'year': self.parse_year(item.get('year')),
                    'rating': item.get('rating', {}).get('value'),
                    'douban_id': item.get('id'),
                    'media_type': media_type
                })
            return result
        except Exception as e:
            logger.error(f"获取豆瓣{media_type}数据失败: {str(e)}")
            return []

    def parse_year(self, year_str):
        if not year_str:
            return ""
        try:
            return year_str.replace('年', '').strip()
        except:
            return ""

def create_plugin(mb: MovieBotServer):
    return HotMediaDaily(mb)
