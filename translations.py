lang = "zh"

def translate(key: str = ""):
    if key in translation:
        if lang in translation[key]:
            return translation[key][lang]
        elif "zh" in translation[key]:
            return translation[key]["zh"]
        else:
            return key
    else:
        return key

translation = {
    "error": {
        "zh": "错误：",
        "en": "Error: ",
        "ja": "エラー："
    },
    "error.config.load": {
        "zh": "加载配置`CONFIG`时有问题",
        "en": "Failed to load config `CONFIG`",
        "ja": "設定`CONFIG`の読み込みに失敗しました"
    },
    "error.config.save": {
        "zh": "保存配置`CONFIG`时有问题",
        "en": "Failed to save config `CONFIG`",
        "ja": "設定`CONFIG`の保存に失敗しました"
    },
    "error.config.not_valid": {
        "zh": "配置中的`VAR`有问题",
        "en": "`VAR` in config was not valid",
        "ja": "設定内の`VAR`が無効です"
    },
    "error.load": {
        "zh": "加载CATEGORY时`KEY`有问题，以`DEFAULT`代替",
        "en": "Failed to load CATEGORY because `KEY` was wrong, replacing with `DEFAULT`",
        "ja": "`KEY`が正しくないため、CATEGORYの読み込みに失敗しました"
    },
    "error.load.message": {
        "zh": "消息",
        "en": "message",
        "ja": "メッセージ",
    },
    "error.load.provider": {
        "zh": "提供商",
        "en": "provider",
        "ja": "プロバイダー"
    },
    "error.load.model": {
        "zh": "模型",
        "en": "model",
        "ja": "モデル"
    },
    "error.load.chat": {
        "zh": "对话",
        "en": "chat",
        "ja": "チャット"
    },
    "error.provider.no": {
        "zh": "未添加提供商或未选择模型。请输入/models或/providers并确保至少有一个提供商和一个模型。",
        "en": "",
        "ja": ""
    },
    "whisper": {
        "zh": "……",
        "en": "... ",
        "ja": "……"
    },
    "welcome": {
        "zh": "欢迎来到TwT2.3！\n（语言不保证100%准确）\n (The language is not guaranteed to be 100% accurate) ",
        "en": "Welcome to TwT2.3! \n (The translation into other languages is done by AI and is not guaranteed to be 100% accurate) \n（其它语言翻译由AI完成，不保证100%准确）",
        "ja": "TwT2.3へようこそ！\n（他の言語への翻訳はAIによって行われており、100%正確であることを保証するものではありません）\n（其它语言翻译由AI完成，不保证100%准确）\n (The translation into other languages is done by AI and is not guaranteed to be 100% accurate) "
    },
    "help": {
        "zh": """/new - 创建新的对话
/models - 添加提供商或选择当前模型
/providers - 添加服务提供商或选择默认模型
/exit - 退出""",
        "en": """/new - Create a new chat
/models - Add service providers or select a current model
/providers - Add service providers or select a default model
/exit - Exit the program""",
        "ja": """/new - 新しいチャットを開始
/models - サービスプロバイダーを追加、または利用モデルを選択
/providers - サービスプロバイダーを追加、またはデフォルトモデルを選択
/exit - プログラムを終了"""
    },
    "help.models": {
        "zh": "O键 - 添加一个提供商",
        "en": "",
        "ja": ""
    },
    "chat.title": {
        "zh": "（TITLE）",
        "en": "(TITLE)",
        "ja": "（TITLE）"
    },
    "chat.new": {
        "zh": "新对话",
        "en": "New Chat",
        "ja": "新規チャット"
    },
    "providers.empty": {
        "zh": "（无）",
        "en": " (Empty) "
    },
    "provider.name.ask": {
        "zh": "请输入提供商名称（直接按下回车则取消）："
    },
    "provider.url.ask": {
        "zh": "请输入提供商API地址（直接按下回车则取消；需符合[bold red]https://[/]api.openai.com/v1[bold red]/[/]格式）："
    },
    "provider.key.ask": {
        "zh": "（请输入密钥（直接按下回车则取消）："
    },
    "provider.type.ask": {
        "zh": "请选择提供商类型"
    },
    "stage.none": {
        "zh": "关",
        "en": "Off",
        "ja": "関"
    },
    "stage.enabled": {
        "zh": "开",
        "en": "On",
        "ja": "開"
    },
    "stage.high": {
        "zh": "高",
        "en": "High",
        "ja": "高"
    },
    "stage.max": {
        "zh": "最大",
        "en": "Max",
        "ja": "最大"
    },
    "stage.medium": {
        "zh": "中",
        "en": "Medium",
        "ja": "中"
    },
    "stage.low": {
        "zh": "低",
        "en": "Low",
        "ja": "低"
    },
    "stage.auto": {
        "zh": "自动",
        "en": "Auto",
        "ja": "自動"
    }
}