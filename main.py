import difflib
import random
import json
import os
from typing import List, Optional

import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

AVAILABLE_SOURCES = {
    "gitlab": {
        "custom": "https://gitlab.com/infinitefusion/sprites/-/raw/master/CustomBattlers/{n}/",
        "autogen": "https://gitlab.com/infinitefusion/sprites/-/raw/master/Battlers/"
    },
    "fusioncalc": {
        "custom": "https://fusioncalc.com/wp-content/themes/twentytwentyone/pokemon/custom-fusion-sprites-main/CustomBattlers/",
        "autogen": "https://fusioncalc.com/wp-content/themes/twentytwentyone/pokemon/autogen-fusion-sprites-master/Battlers/"
    }
}

@register("pokemon_fusion", "sugayoiya", "宝可梦融合插件", "1.0.0")
class PokemonFusionPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.pokemon_data = {}
        self.config = {
            "source": "gitlab"
        }
        
    async def initialize(self):
        """初始化插件，加载宝可梦数据"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(current_dir, "pokemons.json"), "r", encoding="utf8") as f:
                self.pokemon_data = json.load(f)
            logger.info("宝可梦数据加载成功")
        except Exception as e:
            logger.error(f"加载宝可梦数据失败: {e}")
            
    def get_similar_names(self, name: str, limit: int = 3) -> List[str]:
        """获取相似的宝可梦名字"""
        if not self.pokemon_data:
            return []
        names = list(self.pokemon_data.keys())
        similarity_scores = [(n, difflib.SequenceMatcher(None, name, n).quick_ratio()) for n in names]
        similarity_scores.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in similarity_scores[:limit]]
        
    async def get_fusion_image(self, fusion_id: str) -> Optional[str]:
        """获取融合图片URL"""
        head_id = fusion_id.split(".")[0]
        
        async def check_image_exists(url: str) -> bool:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        return response.status == 200
            except Exception as e:
                logger.error(f"检查图片URL失败: {e}")
                return False
                
        # 尝试获取自定义融合图片
        fusion_url = AVAILABLE_SOURCES[self.config["source"]]["custom"].format(n=head_id) + fusion_id
        if await check_image_exists(fusion_url):
            return fusion_url
            
        # 尝试获取自动生成的融合图片
        fallback_url = AVAILABLE_SOURCES[self.config["source"]]["autogen"] + head_id + "/" + fusion_id
        if await check_image_exists(fallback_url):
            return fallback_url
            
        # 如果都失败了，返回问号图片
        return "https://infinitefusion.gitlab.io/pokemon/question.png"

    @filter.command("融合", aliases=["宝可梦融合"])
    async def fusion(self, event: AstrMessageEvent):
        """宝可梦融合！发送"宝可梦1+宝可梦2"来查看它们的融合形态"""
        # 获取命令后的参数部分
        message = event.message_str.strip()
        command = message.split()[0] if message else ""
        message = message[len(command):].strip() if command else ""
        
        def get_pokemon_name(pid: str) -> str:
            """根据ID获取宝可梦名字"""
            for name, pid2 in self.pokemon_data.items():
                if str(pid2) == pid:
                    return name
            return f"#{pid}"

        # 处理随机融合的情况（包括空参数和"随机"命令）
        if not message or message == "随机":
            id1, id2 = [str(random.randint(1, 420)) for _ in range(2)]
        else:
            # 处理指定宝可梦融合的情况
            pokemon_list = message.split("+")
            
            # 如果只输入了一个宝可梦，随机选择另一个
            if len(pokemon_list) == 1:
                pokemon = pokemon_list[0].strip()
                if pokemon not in self.pokemon_data:
                    similar_names = self.get_similar_names(pokemon)
                    chain = [
                        Comp.At(qq=event.get_sender_id()),
                        Comp.Plain(f" 未找到宝可梦 {pokemon}！\n"),
                        Comp.Plain(f"你要找的是不是：{'、'.join(similar_names)}？")
                    ]
                    yield event.chain_result(chain)
                    return
                    
                id1 = str(self.pokemon_data[pokemon])
                id2 = str(random.randint(1, 420))
            
            # 处理两个宝可梦的情况
            elif len(pokemon_list) == 2:
                pokemon_list = [p.strip() for p in pokemon_list]
                not_found_pokemons = []
                
                for pokemon in pokemon_list:
                    if pokemon not in self.pokemon_data:
                        similar_names = self.get_similar_names(pokemon)
                        not_found_pokemons.append(f"未找到 {pokemon}！尝试以下结果：{'、'.join(similar_names)}")
                        
                if not_found_pokemons:
                    chain = [
                        Comp.At(qq=event.get_sender_id()),
                        Comp.Plain(" " + "\n".join(not_found_pokemons))
                    ]
                    yield event.chain_result(chain)
                    return
                    
                id1 = str(self.pokemon_data[pokemon_list[0]])
                id2 = str(self.pokemon_data[pokemon_list[1]])
            
            else:
                chain = [
                    Comp.At(qq=event.get_sender_id()),
                    Comp.Plain(" 请输入一个或两个宝可梦的名字\n"),
                    Comp.Plain("例如：/融合 皮卡丘+妙蛙种子\n"),
                    Comp.Plain("或者：/融合 皮卡丘（将随机选择另一个宝可梦）")
                ]
                yield event.chain_result(chain)
                return
            
        # 生成融合ID并去重
        fusion_ids = {f"{id1}.{id2}.png", f"{id2}.{id1}.png"}
        
        try:
            # 先检查图片是否可访问
            image_urls = []
            for fusion_id in fusion_ids:
                image_url = await self.get_fusion_image(fusion_id)
                if image_url:
                    image_urls.append(image_url)
            
            if not image_urls:
                chain = [
                    Comp.At(qq=event.get_sender_id()),
                    Comp.Plain(" 抱歉，获取融合图片失败，请稍后再试。")
                ]
                yield event.chain_result(chain)
                return
                
            # 获取宝可梦名字并构建消息链
            name1 = get_pokemon_name(id1)
            name2 = get_pokemon_name(id2)
            chain = [
                Comp.At(qq=event.get_sender_id()),
                Comp.Plain(f" 正在为你融合 {name1} 和 {name2}：\n")
            ]
            
            # 添加所有融合图片到消息链
            for image_url in image_urls:
                chain.append(Comp.Image.fromURL(image_url))
                chain.append(Comp.Plain("\n"))
                
            yield event.chain_result(chain)
            
        except Exception as e:
            logger.error(f"融合图片处理失败: {e}")
            chain = [
                Comp.At(qq=event.get_sender_id()),
                Comp.Plain(" 抱歉，处理融合图片时出错，请稍后再试。")
            ]
            yield event.chain_result(chain)
            
    @filter.command("宝可梦切换源", aliases=["融合切换源"])
    async def switch_source(self, event: AstrMessageEvent):
        """切换融合图片的来源（在 gitlab 和 fusioncalc 之间切换）"""
        sources = list(AVAILABLE_SOURCES.keys())
        current_index = sources.index(self.config["source"])
        next_index = (current_index + 1) % len(sources)
        
        old_source = self.config["source"]
        self.config["source"] = sources[next_index]
        
        chain = [
            Comp.At(qq=event.get_sender_id()),
            Comp.Plain(f" 已将图片源从 {old_source} 切换为 {self.config['source']}")
        ]
        yield event.chain_result(chain)
        
    async def terminate(self):
        """插件卸载时的清理工作"""
        self.pokemon_data = {}
