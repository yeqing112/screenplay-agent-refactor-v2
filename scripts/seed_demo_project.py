"""Seed a demo project for phase-1 canvas integration."""
from __future__ import annotations

import json

from models import (
    Book,
    BookBible,
    CharacterProfile,
    EpisodeOutline,
    QAResult,
    Script,
    Session,
    StoryboardShot,
    VisualEraSpec,
    VisualLocation,
    VisualMakeup,
    VisualProp,
    init_db,
)


BOOK_TITLE = "最大的傲慢"
BOOK_FILENAME = "demo_maximum_arrogance.txt"
BOOK_BIBLE_TEXT = (
    "世界观：当代都市背景，地点为普通中国二线城市路边。\n"
    "基调：温情现实主义，底层与中产阶级的碰撞，通过日常小事揭示深刻人性。\n"
    "核心冲突：社会阶层差异带来的偏见与误解，最终靠真诚善意化解。"
)


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def reset_book(session, book_id: int) -> None:
    for model in [
        BookBible,
        CharacterProfile,
        EpisodeOutline,
        Script,
        QAResult,
        StoryboardShot,
        VisualEraSpec,
        VisualLocation,
        VisualMakeup,
        VisualProp,
    ]:
        session.query(model).filter(model.book_id == book_id).delete()


def main() -> None:
    init_db()

    with Session() as session:
      book = session.query(Book).filter(Book.title == BOOK_TITLE).first()
      if not book:
          book = Book(
              title=BOOK_TITLE,
              filename=BOOK_FILENAME,
              chapter_count=1,
              total_words=178,
              status="storyboarded",
          )
          session.add(book)
          session.flush()
      else:
          book.filename = BOOK_FILENAME
          book.chapter_count = 1
          book.total_words = 178
          book.status = "storyboarded"
          reset_book(session, book.id)

      session.add(BookBible(book_id=book.id, content=BOOK_BIBLE_TEXT))

      session.add(CharacterProfile(
          book_id=book.id,
          name="老头",
          aliases=dumps([]),
          gender="男性",
          age_range="70岁左右",
          identity="收废品老人",
          signature_outfit="深色旧夹克、宽松黑裤、老式布鞋",
          accessories="草帽",
          temperament="朴素、隐忍、倔强",
          speech_style="慢条斯理，但关键时刻很有分量",
          visual_prompt_zh="七十岁中国老人，满脸皱纹，质朴克制，写实影视定妆风格。",
      ))
      session.add(CharacterProfile(
          book_id=book.id,
          name="路虎车主",
          aliases=dumps([]),
          gender="男性",
          age_range="40岁左右",
          identity="中产车主",
          signature_outfit="蓝色 Polo 衫、深卡其休闲裤、皮鞋",
          accessories="太阳镜、金属腕表",
          temperament="自信、体面、优越感明显",
          speech_style="语速快、带轻微命令感",
          visual_prompt_zh="四十岁中国中年男性，体面整洁，略带轻蔑，写实影视人物设定图。",
      ))

      session.add(EpisodeOutline(
          book_id=book.id,
          genre="short_drama",
          episode=1,
          title="最大的傲慢",
          core_event="路虎车主轻视收废品老人，最后被一把车钥匙打脸。",
          opening_hook="老头推着生锈三轮车上场。",
          core_conflict="身份偏见引发的对峙。",
          climax="老人按下车钥匙，另一辆黑色轿车亮灯。",
          ending_hook="车主愣在原地，反思自己的傲慢。",
          characters=dumps(["老头", "路虎车主"]),
          scenes=dumps(["城市道路边"]),
          raw_content="单集短剧大纲：一个普通路边冲突引出阶层偏见与人物反转。",
      ))

      session.add(Script(
          book_id=book.id,
          genre="short_drama",
          episode=1,
          content=(
              "【第 1 集：最大的傲慢】\n\n"
              "一个衣着朴素的老头推着生锈三轮车经过城市道路边。\n"
              "一辆黑色路虎疾驰而过，车主下车后对老人出言不逊。\n"
              "老人没有争辩，只拿出一把车钥匙，按下后旁边的黑色轿车亮灯。"
          ),
          word_count=178,
          status="done",
      ))

      session.add(QAResult(
          book_id=book.id,
          episode=1,
          error_count=0,
          result=dumps({
              "overall_score": 9.2,
              "suggestions": ["开场动作足够清晰，可继续保持镜头节奏上的克制。"],
          }),
      ))

      session.add(VisualEraSpec(
          book_id=book.id,
          timeline_start="2000年代（当代）",
          timeline_end="2020年代（当代）",
          clothing_spec="底层劳动者旧夹克与布鞋，中产车主穿着体面休闲。",
          color_palette="灰蓝、土黄、金属黑为主。",
          architecture_spec="普通二线城市道路边，多层居民楼、临街店铺、行道树。",
          prop_spec="生锈三轮车、黑色路虎、智能车钥匙等日常道具。",
          color_curve="前段冷静克制，中段对立升级，后段反转后稍稍转暖。",
      ))

      session.add(VisualLocation(
          book_id=book.id,
          book_title=BOOK_TITLE,
          name="城市道路边",
          category="户外/街道",
          style="现实主义、普通日常",
          description="普通二线城市道路边，人行道与非机动车道相邻，灰色水泥路面，行道树和路边停车共同构成生活街景。",
          color_palette="灰白、灰蓝、点缀绿色",
          lighting_mood="自然日光，明亮但不过曝",
          visual_prompt_zh="当代城市道路边实景，灰色路面与行道树并置，普通居民楼和停放车辆构成低调真实的生活感。",
          core_prompt_zh="普通中国二线城市路边，写实、生活化、影视质感。",
          shot_ids=dumps([11, 12, 13, 14, 15]),
      ))

      session.add(VisualProp(
          book_id=book.id,
          book_title=BOOK_TITLE,
          name="生锈三轮车",
          category="交通工具",
          description="老旧载货三轮车，车斗有锈迹，链条略松，轮胎磨损，车斗中放着废纸箱。",
          visual_prompt_zh="生锈三轮车多角度道具图，金属锈迹明显，结构老旧，写实展示风格。",
          core_prompt_zh="旧三轮车，道具设定图，写实。",
          importance="high",
          shot_ids=dumps([11]),
      ))
      session.add(VisualProp(
          book_id=book.id,
          book_title=BOOK_TITLE,
          name="黑色路虎",
          category="交通工具",
          description="黑色 SUV，车身较高，黑色金属漆，深色车窗。",
          visual_prompt_zh="黑色 SUV 多角度道具图，现代中产气质，写实产品展示。",
          core_prompt_zh="黑色路虎风格 SUV，道具设定图，写实。",
          importance="medium",
          shot_ids=dumps([12, 13, 15]),
      ))
      session.add(VisualProp(
          book_id=book.id,
          book_title=BOOK_TITLE,
          name="车钥匙",
          category="信物/关键道具",
          description="黑色智能车钥匙，塑料外壳，按键式遥控结构，是剧情反转的关键细节。",
          visual_prompt_zh="黑色车钥匙多角度道具图，按键清晰，写实产品拍摄质感。",
          core_prompt_zh="智能车钥匙，道具特写，写实。",
          importance="high",
          shot_ids=dumps([14, 15]),
      ))

      session.add(VisualMakeup(
          book_id=book.id,
          book_title=BOOK_TITLE,
          episode=1,
          character_name="老头",
          refined_outfit="深色旧夹克、宽松黑裤、老式布鞋",
          refined_accessories="草帽",
          makeup_spec="老年妆明显，法令纹和眼下细纹突出，嘴唇略干裂。",
          hair_style="花白短发，略显凌乱",
          expression_mood="疲惫但克制",
          visual_prompt_zh="六宫格人物定妆：七十岁中国老人，朴素、坚韧、略显疲惫，影视级写实质感。",
          shot_ids=dumps([11, 12, 14, 15]),
      ))
      session.add(VisualMakeup(
          book_id=book.id,
          book_title=BOOK_TITLE,
          episode=1,
          character_name="路虎车主",
          refined_outfit="蓝色 Polo 衫、深卡其休闲裤、深棕皮鞋",
          refined_accessories="太阳镜、金属腕表",
          makeup_spec="中年男性，面容整洁，保持都市体面感。",
          hair_style="短发整齐，发际线略后移",
          expression_mood="自信、略带压迫感",
          visual_prompt_zh="六宫格人物定妆：四十岁中国中年男性，着装体面，自信中带轻蔑，影视级写实质感。",
          shot_ids=dumps([13, 15]),
      ))

      shots = [
          {
              "shot_id": 11,
              "scene_name": "城市道路边",
              "duration": 3,
              "camera_angle": "全景",
              "camera_movement": "固定",
              "transition": "硬切",
              "lighting": "自然光，明亮",
              "sound_effects": ["车流声", "环境底噪"],
              "bgm_mood": "平淡铺陈",
              "dialogue": "",
              "start_state": "老头推着三轮车上场",
              "action_process": "缓慢前行，链条轻响，纸箱轻微晃动",
              "end_state": "停在路边调整呼吸",
              "visual_prompt_static": "城市道路边，一位约七十岁的老头穿着深色旧夹克，推着生锈三轮车，背景是灰白居民楼与行道树，午后自然光，写实电影感。",
              "visual_prompt_motion": "固定机位，老头从画面右侧缓慢推车进入，链条轻响，车斗里的纸箱轻微晃动。",
          },
          {
              "shot_id": 12,
              "scene_name": "城市道路边",
              "duration": 4,
              "camera_angle": "中景",
              "camera_movement": "摇镜",
              "transition": "硬切",
              "lighting": "自然光",
              "sound_effects": ["汽车喇叭声"],
              "bgm_mood": "轻微紧张",
              "dialogue": "老头：“按什么按，没看见老人家在走路吗？”",
              "start_state": "老头停下脚步，看向路虎方向",
              "action_process": "人物转身，表情从困惑变成不满",
              "end_state": "盯住停下的路虎",
              "visual_prompt_static": "老头转头看向画外的黑色路虎，神情克制却不悦，背景街道略虚化，焦点压在人物表情上。",
              "visual_prompt_motion": "镜头从老头侧脸缓慢摇向路虎停车方向，带出人物视线和紧张气氛。",
          },
          {
              "shot_id": 13,
              "scene_name": "城市道路边",
              "duration": 5,
              "camera_angle": "近景",
              "camera_movement": "手持微晃",
              "transition": "硬切",
              "lighting": "高亮日光",
              "sound_effects": ["关车门声", "脚步声"],
              "bgm_mood": "对立升级",
              "dialogue": "路虎车主：“老头，你三轮车挡道了，挪一挪。”",
              "start_state": "路虎车主下车走近",
              "action_process": "步伐自信，目光上下打量老人",
              "end_state": "站到老头面前，保持压迫距离",
              "visual_prompt_static": "路虎车主居高临下看着老头，神情轻蔑，背后是锃亮的黑色 SUV，形成强烈身份反差。",
              "visual_prompt_motion": "手持镜头跟随路虎车主下车、关门、逼近，镜头略带压迫感。",
          },
          {
              "shot_id": 14,
              "scene_name": "城市道路边",
              "duration": 6,
              "camera_angle": "特写",
              "camera_movement": "缓慢推进",
              "transition": "硬切",
              "lighting": "高反差",
              "sound_effects": ["钥匙碰撞声"],
              "bgm_mood": "悬念抬升",
              "dialogue": "老头：“年轻人，知道这车钥匙是什么样的吗？”",
              "start_state": "老头平静看着路虎车主",
              "action_process": "伸手入怀，缓慢取出钥匙，举到对方面前",
              "end_state": "钥匙停在半空，情绪反转前夕",
              "visual_prompt_static": "老头粗糙的手举着一把黑色车钥匙特写，逆光勾边，背景虚化，强调钥匙和老人手部纹理。",
              "visual_prompt_motion": "镜头从钥匙特写慢慢拉到老人脸部，突出平静与笃定。",
          },
          {
              "shot_id": 15,
              "scene_name": "城市道路边",
              "duration": 4,
              "camera_angle": "中景",
              "camera_movement": "震动切换",
              "transition": "硬切",
              "lighting": "日光正常",
              "sound_effects": ["车辆解锁声"],
              "bgm_mood": "戏剧反转",
              "dialogue": "",
              "start_state": "路虎车主仍然不屑",
              "action_process": "老头按下钥匙，旁边黑色轿车车灯亮起",
              "end_state": "路虎车主愣在原地",
              "visual_prompt_static": "按下钥匙的瞬间，旁边黑色轿车灯光闪烁，路虎车主从轻蔑转为震惊，形成戏剧反差。",
              "visual_prompt_motion": "快速切换老人按钥匙、远处轿车亮灯、两人表情变化，制造反转节奏。",
          },
      ]

      for shot in shots:
          session.add(StoryboardShot(
              book_id=book.id,
              episode=1,
              scene_name=shot["scene_name"],
              shot_id=shot["shot_id"],
              dialogue=shot["dialogue"],
              duration=shot["duration"],
              camera_angle=shot["camera_angle"],
              camera_movement=shot["camera_movement"],
              transition=shot["transition"],
              lighting=shot["lighting"],
              sound_effects=dumps(shot["sound_effects"]),
              bgm_mood=shot["bgm_mood"],
              start_state=shot["start_state"],
              action_process=shot["action_process"],
              end_state=shot["end_state"],
              visual_prompt_static=shot["visual_prompt_static"],
              visual_prompt_motion=shot["visual_prompt_motion"],
              asset_status="pending",
          ))

      session.commit()
      print(f"Seeded demo project: {BOOK_TITLE} (book_id={book.id})")


if __name__ == "__main__":
    main()
