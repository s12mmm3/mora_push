import requests
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

class MoraReleaseChecker:
    """用于获取Mora.jp上指定日期发布的所有专辑"""
    
    @staticmethod
    def get_albums(
        target_date: datetime.date,
        region: Optional[str] = None,
        deduplicate: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取指定日期发布的所有专辑
        
        :param target_date: 要查询的日期
        :param region: 地区代码，None则使用实例默认值
        :param deduplicate: 是否去重，None则使用实例默认值
        :return: 专辑字典列表
        """
        
        newReleaseList = []
        page = 1
        has_more_pages = True
        
        target_date_str = target_date.strftime("%Y/%m/%d") + " 00:00:00"
        timestamp = int(time.mktime(target_date.timetuple())) * 1000
        
        while has_more_pages:
            url = f"https://cf.mora.jp/contents/data/newrelease/web/newrelease/newRelease_{region}_{page:04d}.jsonp?_{timestamp}"
            
            try:
                response = requests.get(url)
                response.raise_for_status()
                
                json_data = response.text.replace("moraCallback(", "").rstrip(");")
                data = json.loads(json_data)
                
                current_page_albums = []
                for album in data["newReleaseList"]:
                    if album["dispStartDate"] == target_date_str:
                        current_page_albums.append(album)
                
                newReleaseList.extend(current_page_albums)
                
                if page >= data["splitFileCnt"]:
                    has_more_pages = False
                else:
                    page += 1
                    
                if data["newReleaseList"] and data["newReleaseList"][-1]["dispStartDate"] < target_date_str:
                    has_more_pages = False
                    
            except Exception as e:
                print(f"获取第{page}页时出错: {e}")
                break
        
        if deduplicate and newReleaseList:
            seen = set()
            deduplicated_list = []
            
            for album in newReleaseList:
                identifier = (
                    album["artistName"],
                    album["dispStartDate"],
                    album["title"],
                    album["trackCount"]
                )
                
                if identifier not in seen:
                    seen.add(identifier)
                    deduplicated_list.append(album)
            
            return deduplicated_list
        
        return newReleaseList