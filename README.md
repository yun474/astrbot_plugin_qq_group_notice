# QQ 官方群进退通知

云云写的 AstrBot QQ 官方机器人群通知插件。它不修改 AstrBot 源码，通过一个可卸载的运行时事件桥补齐普通群成员进退事件。

## 功能

- 机器人被拉进新群时发送打招呼消息；
- 普通成员进群时发送欢迎消息；
- 普通成员退群时发送退群通知；
- 三种通知分别提供开关和自定义文本；
- 支持群黑名单、群白名单和不过滤三种模式；
- 同时支持 `qq_official` WebSocket 和 `qq_official_webhook`；
- 按 `event_id` 去重，避免 Webhook 重投造成连续欢迎两遍；
- 尽力从事件字段、普通群消息缓存和手动群名称映射中取得昵称。

最低 AstrBot 版本：`4.26.6`。

## 安装

将整个 `astrbot_plugin_qq_group_notice` 目录放入：

```text
AstrBot/data/plugins/astrbot_plugin_qq_group_notice
```

然后在 AstrBot 插件管理页重载插件，或重启 AstrBot。

平台必须使用：

- `qq_official`
- `qq_official_webhook`

NapCat/OneBot 等适配器不在本插件处理范围内。

## 配置示例

机器人入群：

```text
大家好，我是 {bot_name}，很高兴加入 {group_display}！
邀请人：{operator_display}
```

成员进群：

```text
欢迎 {member_at} 加入 {group_display}！
昵称：{member_nickname}
```

成员退群：

```text
{member_display} 已退出 {group_display}。
时间：{event_time}
```

模板里写了插件不认识的占位符时，插件会原样保留它，不会因为一个大括号把整条消息干碎。

## 占位符

### 群信息

| 占位符 | 内容 | 获取与回退方式 |
| --- | --- | --- |
| `{group_id}` | 群 OpenID | 直接读取事件，和 `{group_openid}` 相同 |
| `{group_openid}` | 群 OpenID | QQ 官方群标识，不是数字群号 |
| `{group_name}` | 群名称 | 手动群名称映射 → 事件字段 → 运行期缓存 → 群 OpenID |
| `{group_nickname}` | 群名称 | `{group_name}` 的别名 |
| `{group_display}` | 最适合展示的群名 | 优先群名称，没有时使用群 OpenID |

QQ 官方普通群事件通常不提供稳定的群名称查询接口。若希望 `{group_name}` 始终好看，请在“群名称映射”中填写：

```text
第一串群OpenID=主人快乐老家
第二串群OpenID=云云摸鱼分部
```

每行一条，等号左边是 `group_openid`，右边是希望显示的群名称。

### 成员信息

| 占位符 | 内容 | 获取与回退方式 |
| --- | --- | --- |
| `{member_openid}` | 进群或退群成员 OpenID | 直接读取事件 |
| `{user_id}` | 成员 OpenID | `{member_openid}` 的别名 |
| `{user_openid}` | 成员 OpenID | `{member_openid}` 的别名 |
| `{member_nickname}` | 成员昵称/群昵称 | 事件字段 → 本次运行期间的群消息昵称缓存 → 成员 OpenID |
| `{user_nickname}` | 成员昵称/群昵称 | `{member_nickname}` 的别名 |
| `{member_display}` | 最适合展示的成员名 | 优先昵称，没有时使用成员 OpenID，再没有则显示“未知成员” |
| `{member_at}` | 尝试 @ 该成员 | 输出 QQ 官方格式 `<@成员OpenID>`；退群后通常无法真正 @ 到对方 |

### 操作人信息

操作人通常是邀请机器人或处理成员变动的用户。用户主动退群时，QQ 可能不提供独立操作人。

| 占位符 | 内容 | 获取与回退方式 |
| --- | --- | --- |
| `{operator_openid}` | 操作人 OpenID | 读取 `op_member_openid` |
| `{op_member_openid}` | 操作人 OpenID | `{operator_openid}` 的别名 |
| `{operator_nickname}` | 操作人昵称 | 事件字段 → 昵称缓存 → 操作人 OpenID |
| `{operator_display}` | 最适合展示的操作人名称 | 优先昵称，没有时使用 OpenID |
| `{operator_at}` | 尝试 @ 操作人 | 输出 `<@操作人OpenID>` |

### 事件与机器人

| 占位符 | 内容 |
| --- | --- |
| `{event_type}` | `bot_join`、`member_join` 或 `member_leave` |
| `{event_id}` | QQ 官方事件 ID |
| `{event_time}` | 格式化后的本地时间 |
| `{timestamp}` | QQ 原始时间字段 |
| `{bot_name}` | botpy 登录信息中可见的机器人名称；拿不到时显示“机器人” |

## 昵称为什么可能只显示 OpenID

插件会尽力获取昵称，但 QQ 官方普通群事件不保证携带昵称或群名：

1. 先读取事件里的 `nickname`、`member_nickname`、`group_name` 等可能字段；
2. 用户在本次 AstrBot 运行期间说过话时，缓存 `event.get_sender_name()`；
3. 群名称可以通过“群名称映射”稳定指定；
4. 都拿不到时回退到 OpenID，保证消息不会出现空洞。

昵称缓存仅保存在内存中，重启后清空，也不会保存聊天内容。新成员第一次进群时尚未说过话，而 QQ 事件又没给昵称，就只能显示 OpenID。这是上游数据边界，不是云云偷懒没写。

## 群黑白名单

“群过滤模式”支持：

- `disabled`：所有群生效；
- `blacklist`：黑名单里的群不发送；
- `whitelist`：只在白名单里的群发送。

黑白名单填写的是 `group_openid`，支持逗号、空格或换行分隔：

```text
GROUP_OPENID_A
GROUP_OPENID_B
```

启用白名单但列表为空时，所有群都会被拒绝。这是故意的，免得配置漏了以后全群乱欢迎。

AstrBot 管理员可以在目标群发送：

```text
/群通知信息
```

插件会返回当前群 OpenID、已解析的群名称以及黑白名单过滤结果，省得主人在日志里刨那串 ID。

## 事件桥说明

当前 AstrBot 原生 QQ 适配器已经启用 Public Messages Intent，但没有把 `GROUP_MEMBER_ADD` 和 `GROUP_MEMBER_REMOVE` 注册进 botpy 的解析表。本插件在运行时完成两件事：

1. 为 botpy `ConnectionState` 补充普通群成员进退事件解析器；
2. 为每个原生 QQ 平台实例绑定通知回调。

插件卸载时会恢复自己绑定的回调和类方法，不写入、不替换 AstrBot 源码文件。如果未来 AstrBot 或 botpy 原生支持这些事件，插件会检测已有解析器并跳过自己的解析补丁。

## 排错

如果机器人入群通知正常，但普通成员进退群没有任何反应：

1. 开启插件的“调试日志”；
2. 确认机器人使用 `qq_official` 或 `qq_official_webhook`；
3. 确认群没有被黑白名单过滤；
4. 检查 QQ 开放平台是否向当前机器人开放并下发 `GROUP_MEMBER_ADD` / `GROUP_MEMBER_REMOVE`；
5. 搜索日志中的 `[QQ群通知]`。

腾讯没有下发事件时，插件无法凭空知道谁进群了。插件也不会通过轮询群成员列表瞎猜，这样既浪费接口额度，还容易把临时网络错误当成退群。

## 开发检查

```powershell
python -m compileall -q .
python -m json.tool _conf_schema.json
python -m unittest discover -s tests -v
```

## License

MIT
