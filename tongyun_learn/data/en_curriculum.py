"""云芽英语 v1 课表种子：开发英语单元 1–3，加一条生活英语旁路。

词和例句是手写的真实开发用语，不是占位符。量是一小批，够把毕业门槛和队列跑通。
"""

from typing import Any

DEFAULT_GRADUATE_RULE: dict[str, Any] = {
    "review_ratio": 0.8,
    "recent_days": 3,
    "recent_accuracy": 0.85,
    "nail_streak": 3,
}

LIFE_FRACTION = 0.2
DEFAULT_TARGET = 20
EASIER_TARGET = 10
TRACK_DEV = "en"
TRACK_LIFE = "en-life"
DECK_NAME = "yun-ya:en"
SEED_VERSION = 1

# 主线毕业后才允许生活词进入每日队列，且不超过 LIFE_FRACTION。
LIFE_AFTER_DEV_ORD = 3


def _w(lemma: str, phonetic: str, pos: str, cn: str, en: str, zh: str) -> dict[str, Any]:
    return {
        "lemma": lemma,
        "phonetic": phonetic,
        "pos": pos,
        "cn": cn,
        "sentences": [{"en": en, "zh": zh}],
    }


def _words(rows: list[tuple[str, str, str, str, str, str]]) -> list[dict[str, Any]]:
    return [_w(*row) for row in rows]


UNITS: list[dict[str, Any]] = [
    {
        "track": TRACK_DEV,
        "ord": 1,
        "kind": "dev",
        "title": "文档高频虚词与动词",
        "words": _words(
            [
                ("read", "/riːd/", "v.", "阅读；读取", "Please read the error message before you retry.", "重试之前请先阅读错误信息。"),
                ("provide", "/prəˈvaɪd/", "v.", "提供", "The API provides a token for each session.", "这个接口为每次会话提供一个令牌。"),
                ("require", "/rɪˈkwaɪə(r)/", "v.", "需要；要求", "This endpoint requires a valid token.", "这个端点需要一个有效令牌。"),
                ("enable", "/ɪˈneɪbl/", "v.", "使能够；启用", "The flag enables verbose logging.", "这个开关会启用详细日志。"),
                ("return", "/rɪˈtɜːn/", "v.", "返回", "The function returns an empty list.", "这个函数返回一个空列表。"),
                ("include", "/ɪnˈkluːd/", "v.", "包含", "The payload includes a user id.", "载荷里包含用户编号。"),
                ("support", "/səˈpɔːt/", "v.", "支持", "This client supports retry on timeout.", "这个客户端支持超时后重试。"),
                ("ensure", "/ɪnˈʃʊə(r)/", "v.", "确保", "Tests ensure the migration is reversible.", "测试用来确保迁移可以回滚。"),
            ]
        ),
    },
    {
        "track": TRACK_DEV,
        "ord": 2,
        "kind": "dev",
        "title": "通用技术词",
        "words": _words(
            [
                ("latency", "/ˈleɪtənsi/", "n.", "延迟", "High latency makes the page feel slow.", "延迟高会让页面显得很慢。"),
                ("throughput", "/ˈθruːpʊt/", "n.", "吞吐量", "Throughput drops when the pool is full.", "池子满了以后吞吐量会下降。"),
                (
                    "deprecated",
                    "/ˈdeprəkeɪtɪd/",
                    "adj.",
                    "已弃用",
                    "This method is deprecated and will be removed.",
                    "这个方法已弃用，以后会删掉。",
                ),
                ("timeout", "/ˈtaɪmaʊt/", "n.", "超时", "The client closed the socket on timeout.", "超时后客户端关掉了套接字。"),
                ("cache", "/kæʃ/", "n.", "缓存", "The cache serves repeated lookups.", "缓存用来响应重复的查询。"),
                ("query", "/ˈkwɪəri/", "n.", "查询", "The query uses an index on user id.", "这条查询用了用户编号上的索引。"),
                ("deploy", "/dɪˈplɔɪ/", "v.", "部署", "We deploy the service after the tests pass.", "测试通过之后我们才部署服务。"),
                ("runtime", "/ˈrʌntaɪm/", "n.", "运行时", "The runtime loads the config at startup.", "运行时在启动时加载配置。"),
            ]
        ),
    },
    {
        "track": TRACK_DEV,
        "ord": 3,
        "kind": "dev",
        "title": "Java 与后端核心",
        "words": _words(
            [
                (
                    "thread-safe",
                    "/ˈθred seɪf/",
                    "adj.",
                    "线程安全的",
                    "The pool is thread-safe for shared use.",
                    "这个池子可以安全地被多线程共用。",
                ),
                ("deadlock", "/ˈdedlɒk/", "n.", "死锁", "A deadlock stalls both threads.", "死锁会让两条线程都停住。"),
                ("mutex", "/ˈmjuːteks/", "n.", "互斥锁", "The mutex guards the shared counter.", "互斥锁保护着共享计数器。"),
                ("pool", "/puːl/", "n.", "池", "The connection pool reuses open sockets.", "连接池会复用已经打开的套接字。"),
                ("heap", "/hiːp/", "n.", "堆", "The heap stores objects created at runtime.", "堆存放运行时创建的对象。"),
                ("stack", "/stæk/", "n.", "栈；调用栈", "The stack trace shows the call chain.", "栈追踪会显示调用链。"),
                ("override", "/ˌəʊvəˈraɪd/", "v.", "重写", "Subclasses override this method.", "子类会重写这个方法。"),
                (
                    "callback",
                    "/ˈkælbæk/",
                    "n.",
                    "回调",
                    "The callback runs after the request completes.",
                    "请求完成后会执行回调。",
                ),
            ]
        ),
    },
    {
        "track": TRACK_LIFE,
        "ord": 1,
        "kind": "life",
        "title": "生活英语旁路",
        "words": _words(
            [
                ("meeting", "/ˈmiːtɪŋ/", "n.", "会议", "The meeting starts at nine.", "会议九点开始。"),
                ("deadline", "/ˈdedlaɪn/", "n.", "截止日期", "The deadline is this Friday.", "截止日期是这周五。"),
                ("schedule", "/ˈʃedjuːl/", "n.", "日程", "I will check my schedule.", "我去看一下日程。"),
                ("confirm", "/kənˈfɜːm/", "v.", "确认", "Please confirm the time by email.", "请用邮件确认时间。"),
            ]
        ),
    },
]
