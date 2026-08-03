# 第 01 章 · Python 基础

> **定位：** 面试"开胃菜"，要求必拿分。25 题，由浅入深分六层：语言基石 → 函数 → 迭代与资源管理 → 面向对象 → 异常 → 类型系统。
> **模板与红线：** 遵守 `../README.md` 铁律 4（8 段模板）、铁律 7（叙事红线）。
> **代码示例风格：** Python 3.11+（内置泛型、`X | None`）。

---

## 第一层 · 语言基石（Q1~Q5）

---

#### 【面试题 1】Python 有哪些基本数据类型？可变与不可变的区别是什么？

- **难度：** ⭐
- **一句话答案：** 内置类型分可变与不可变两类：不可变的有 `int` / `float` / `bool` / `str` / `tuple` / `frozenset`（还有 `None` / `bytes`），可变的有 `list` / `dict` / `set` / `bytearray`。区别在于对象创建后内容能否原地修改——不可变对象的"修改"其实是创建新对象。
- **考察点：** 这不是背类型清单，而是考察你是否理解"可变性"是后续一切坑（默认参数陷阱、dict key 要求、函数传参行为）的总根源。
- **参考答案：**
  - 可变对象：内容可原地改，`id()` 不变。`lst.append(1)` 后 `id(lst)` 相同。
  - 不可变对象：任何"修改"都产生新对象。`s = s + "x"` 是让 `s` 指向新字符串，旧字符串等待 GC。
  - 三个推论（面试官想听的）：
    1. dict key / set 元素必须可哈希，可哈希的前提是（通常）不可变——所以 list 不能做 key；
    2. 不可变对象天然线程安全，可自由共享；
    3. 函数内"修改"不可变参数不会影响调用方，而可变参数会（见 Q6）。
- **记忆技巧：** 口诀——"**不可变三族：数、串、组；可变三巨头：列、典、集**"。（数=int/float/bool，串=str/bytes，组=tuple/frozenset；列=list，典=dict，集=set。）
- **面试官追问：**
  1. *tuple 真的完全不可变吗？* → 容器本身不可变，但 `t = ([], )` 里的 list 仍可改：可变性是"浅"的，指引用不可换绑。
  2. *为什么 `s += "x"` 循环拼接慢？* → str 不可变，每次产生新对象并拷贝，O(n²)；应 `"".join(parts)`。
  3. *frozenset 有什么用？* → 可哈希的 set，能做 dict key 或嵌进别的 set。
- **项目关联：** 云合领域层大量使用不可变值对象，如 `domain/academic/context.py` 的 `@dataclass(frozen=True)`——frozen 让实例近似不可变，可安全地跨层传递与缓存。

---

#### 【面试题 2】list / tuple / dict / set 的区别和底层实现？

- **难度：** ⭐⭐
- **一句话答案：** list 是动态数组（可变、有序、按索引 O(1)）；tuple 是定长不可变数组（更省内存、可哈希）；dict 是哈希表（3.7+ 保插入序，查改 O(1)）；set 是"只有 key 没有 value 的哈希表"。
- **考察点：** 能否从"底层结构"推出"操作复杂度"，而不是背复杂度表。
- **参考答案：**
  - **list**：连续内存 + 超配策略（append 摊还 O(1)）；中间插入/删除要搬移元素 O(n)。
  - **tuple**：定长、无超配，内存更紧凑；常量和函数多返回值的默认载体。
  - **dict**：哈希表 + 开放寻址；3.7 起靠额外的紧凑数组保插入序。key 必须可哈希。
  - **set**：复用 dict 的哈希表，只存 key；成员判定 `in` O(1)，是去重和集合运算的首选。
  - 选型一句话：按位置取→list/tuple；按键查→dict；存在性判断/去重→set；不可改且要做 key→tuple。
- **记忆技巧：** 对比表——

  | 结构 | 底层 | 有序 | 可变 | 查找 | 典型场景 |
  |---|---|---|---|---|---|
  | list | 动态数组 | ✅ | ✅ | O(n) | 顺序集合 |
  | tuple | 定长数组 | ✅ | ❌ | O(n) | 常量/复合 key |
  | dict | 哈希表 | ✅(插入序) | ✅ | O(1) | 键值映射 |
  | set | 哈希表 | ❌(概念上) | ✅ | O(1) | 去重/成员判定 |
- **面试官追问：**
  1. *dict 为什么 3.7 后有序？* → 新实现用"紧凑数组存 (hash,key,value) 索引 + 稀疏哈希桶存下标"，遍历紧凑数组即插入序，还更省内存。
  2. *`in` 对 list 和 set 的复杂度差异在大数据量下意味着什么？* → 10 万元素：list 每次全扫 O(n)，set 常数；云合查"某代码是否在白名单"这类判断必须用 set/dict。
  3. *什么时候 tuple 比 list 更合适？* → 作为 dict 的复合 key（如 `(user_id, trade_date)`）、函数多返回值、保证不被下游改坏的常量数据。
- **项目关联：** 云合股票复盘的幂等键就是"user + trade_date"复合键思路（见 `application/stock/review_service.py`），这类复合键天然适合 tuple 或数据库唯一约束承载。

---

#### 【面试题 3】`==` 和 `is` 的区别？字符串驻留（interning）是什么？

- **难度：** ⭐⭐
- **一句话答案：** `==` 比较值（调 `__eq__`），`is` 比较身份（`id()` 是否相同，即是不是同一个对象）。驻留是 CPython 对部分字符串/小整数只存一份的优化，会让两个"看起来相等"的对象 `is` 也成立——这只是实现细节，绝不能依赖。
- **考察点：** 值语义 vs 引用语义；是否知道"is 比较意外为 True"背后的解释器优化。
- **参考答案：**
  - `a == b`：问"内容一样吗"；可被类的 `__eq__` 自定义。
  - `a is b`：问"是同一块内存吗"；不可自定义。
  - CPython 优化：小整数池（约 `-5 ~ 256`）、短标识符样式字符串自动驻留，所以 `a = 100; b = 100; a is b` 为 True——**这是缓存副作用，不是语言承诺**。
  - 唯一正确的 `is` 用法：**与单例比较**，典型就是 `x is None` / `x is not None`（None 是全进程唯一单例）。判断值相等一律用 `==`。
- **记忆技巧：** 类比——`==` 问"**长得像吗**"，`is` 问"**是同一个人吗**"（查身份证 `id`）。双胞胎 == 成立、is 不成立。
- **面试官追问：**
  1. *为什么 `x == None` 不好？* → `__eq__` 可被类重载出意外行为；`is None` 语义精确且更快。
  2. *大整数 1000 为什么有时 is 也是 True？* → 同一作用域/同一行编译时常量折叠，解释器复用了常量对象——仍是实现细节。
  3. *如何自定义 ==？* → 实现 `__eq__`，并遵守 Q17 的 `__hash__` 约定。
- **项目关联：** 云合 DTO 大量用 `x: str | None = None` 风格（如 `application/dto/request/travel.py`），配套校验分支统一写 `if value is not None:`——单例判断用 is，是全库一致的约定。

---

#### 【面试题 4】浅拷贝与深拷贝的区别？

- **难度：** ⭐⭐
- **一句话答案：** 浅拷贝（`copy.copy` / 切片 / `list()` / `dict()`）只复制最外层容器，内层对象仍共享引用；深拷贝（`copy.deepcopy`）递归复制整条对象图，完全独立。
- **考察点：** 是否理解嵌套结构下"改一个、另一个跟着变"的事故机理。
- **参考答案：**

  ```python
  import copy

  a = {"tags": ["a", "b"], "meta": {"pv": 1}}
  shallow = copy.copy(a)      # 或 dict(a)
  deep = copy.deepcopy(a)

  a["tags"].append("c")
  a["meta"]["pv"] = 2
  # shallow: tags 有 "c"、pv 为 2（内层共享）
  # deep:    不受影响（整条图已复制）
  ```

  - 赋值 `b = a` 根本不是拷贝，只是多一个名字指向同一对象。
  - 自定义类可用 `__copy__` / `__deepcopy__` 定制行为。
  - 深拷贝慢且有循环引用风险（deepcopy 内部用 memo 字典处理环）。
- **记忆技巧：** 口诀——"**浅拷贝换壳不换芯，深拷贝连壳带芯全换新**"。
- **面试官追问：**
  1. *`lst[:]` 是浅拷贝还是深拷贝？* → 浅拷贝，只复制最外层。
  2. *dataclass 怎么拷贝？* → `dataclasses.replace(obj, field=new)` 生成改字段的新实例（浅拷贝语义），配合 frozen dataclass 是"不可变更新"的标准姿势。
  3. *什么时候必须深拷贝？* → 要把嵌套结构交给不信任的下游随意改，或做快照存档时。
- **项目关联：** 云合旅行行程的"不可变存档"语义（确认行程后不再被后续编辑影响）正是这一拷贝思想的业务化：存档时刻固化数据快照，草稿继续可变——见 `application/travel/` 的存档相关服务。

---

#### 【面试题 5】切片和推导式有哪些要点？

- **难度：** ⭐
- **一句话答案：** 切片 `seq[start:stop:step]` 是左闭右开、越界不报错、返回新对象（浅拷贝）；推导式是"循环 + 过滤 + 变换"的声明式写法，比 map/filter 更易读，且有独立的局部作用域。
- **考察点：** 基本功熟练度；是否知道负步长、浅拷贝语义、推导式作用域这些细节。
- **参考答案：**
  - 切片：`lst[::-1]` 反转；`lst[:]` 是最外层浅拷贝；切片不产生 IndexError（越界自动截断），但单索引会。
  - 推导式三种：`[f(x) for x in it if cond]`、`{k: v for ...}`、`{x for ...}`；生成器表达式 `(f(x) for x in it)` 不立即求值（见 Q12）。
  - 推导式内循环变量在 Python 3 有独立作用域，不泄漏到外层（Python 2 的坑已修）。
  - 可读性红线：推导式超过两层或逻辑复杂时，退回普通 for 循环——炫技式嵌套推导式是扣分项。
- **记忆技巧：** 口诀——"**左闭右开，负步反转，全切即拷**"。
- **面试官追问：**
  1. *生成器表达式和列表推导式怎么选？* → 只需要迭代一次/数据量大用生成器表达式（惰性、省内存）；需要反复用、要索引/切片用列表。
  2. *`sum(x*x for x in nums)` 比 `sum([...])` 好在哪？* → 不建中间列表，内存 O(1)。
  3. *字典推导式键冲突会怎样？* → 后写覆盖先写，不报错——聚合时注意是否丢数据。
- **项目关联：** 云合 `api/v1/chat.py` 的 SSE 事件流就是生成器表达式的生产级应用：异步生成器逐个 `yield f"data: {json.dumps(event)}\n\n"`，边产出边推送，不为全量事件建中间列表。

---

## 第二层 · 函数（Q6~Q10）

---

#### 【面试题 6】Python 函数参数是值传递还是引用传递？

- **难度：** ⭐⭐
- **一句话答案：** 都不是，准确说法是"**按对象引用传递**"（pass by object reference / 共享传递）：形参和实参指向**同一个对象**。函数内对可变对象的原地修改（`append`）调用方可见；对形参重新赋值（绑定新对象）调用方无感。
- **考察点：** 这是 Python 语义的核心题，面试官要听到"同一个对象、两个名字"这一层，而不是"可变就引用、不可变就值"的错误二分。
- **参考答案：**

  ```python
  def f(lst: list[int], s: str) -> None:
      lst.append(1)   # 调用方可见：同一对象原地改
      s += "x"        # 调用方无感：s 被重新绑定到新字符串
      lst = []        # 调用方无感：lst 只是换绑新对象
  ```

  - Python 一切皆对象，变量是"贴在对象上的标签"；传参 = 把标签也贴一份给形参。
  - 推论：不可变对象在函数间天然"传值般安全"；可变对象默认共享，想隔离就传入副本（`f(lst.copy())`）或改用不可变类型。
- **记忆技巧：** 类比——变量是**便利贴**，对象是**箱子**；传参就是往同一个箱子上多贴一张便利贴。改箱子里的东西（原地改）大家都看到；把便利贴撕下来贴到别的箱子（重新赋值）只有一边变。
- **面试官追问：**
  1. *怎么在函数里"替换"调用方的列表内容？* → 原地切片赋值 `lst[:] = new_items`，而不是 `lst = new_items`。
  2. *为什么默认参数用 None 而不是 []？* → 见 Q8，同一机理。
  3. *多线程下共享可变参数要注意什么？* → 原地修改非原子，需锁或改用不可变/线程安全结构。
- **项目关联：** 云合 `application/stock/pipeline.py` 的 DTO 用 Pydantic 模型承载跨层数据，配合 `ConfigDict(extra="forbid")`——边界处用模型校验 + 显式字段，而不是传递可随意改动的裸 dict，正是对"共享可变对象"风险的工程防御。

---

#### 【面试题 7】`*args` 和 `**kwargs` 是什么？参数顺序规则？

- **难度：** ⭐
- **一句话答案：** `*args` 把多余的位置参数收成 tuple，`**kwargs` 把多余的关键字收成 dict；定义顺序固定为：普通参数 → `*args` → 仅关键字参数 → `**kwargs`。
- **考察点：** 基础语法 + 装饰器/通用包装器的必备前置知识。
- **参考答案：**

  ```python
  def f(a: int, *args: int, flag: bool = False, **kwargs: str) -> None: ...
  f(1, 2, 3, flag=True, x="y")   # args=(2,3), kwargs={"x": "y"}
  ```

  - 调用侧反向用法：`f(*[1, 2], **{"flag": True})` 解包传入。
  - `*` 单独出现在签名里表示"后面的参数只能用关键字传"：`def f(a, *, key: str)`——这是设计清晰 API 的利器。
  - 典型场景：装饰器透传（`def wrapper(*args, **kwargs)`）、变长日志/格式化函数。
- **记忆技巧：** 口诀——"**一星收位置成元组，双星收关键字成字典；定义顺序：普、星、键、双星**"。
- **面试官追问：**
  1. *`def f(*, a: int)` 能怎么调？* → 只能 `f(a=1)`，强制关键字提升可读性。
  2. *`/ `在签名里是什么？* → 仅位置参数标记（3.8+），`def f(a, /, b)` 中 a 不能按关键字传。
  3. *装饰器里为什么要 `functools.wraps`？* → 见 Q9，保留原函数的 `__name__`/`__doc__`。
- **项目关联：** 云合的 FastAPI 路由大多走显式类型化签名而非 `**kwargs`（见 `api/v1/` 各路由），因为显式签名能让 FastAPI 自动生成校验与 OpenAPI 文档——这体现"能用显式就不用变长"的工程取舍。

---

#### 【面试题 8】可变默认参数陷阱：`def f(x=[])` 为什么是坑？

- **难度：** ⭐⭐（高频必考）
- **一句话答案：** 默认参数在 `def` 执行时**只求值一次**，作为函数对象的属性存在。`x=[]` 让所有未传参的调用共享同一个列表，跨调用累积脏数据。正确写法：默认 `None`，函数体内再 `x = [] if x is None else x`。
- **考察点：** 对"def 是运行期语句、默认参数是函数属性"这一机制的理解深度。
- **参考答案：**

  ```python
  def bad(x: list[int] = []) -> list[int]:
      x.append(1)
      return x

  bad()  # [1]
  bad()  # [1, 1] ← 上次的列表被复用！

  def good(x: list[int] | None = None) -> list[int]:
      x = [] if x is None else x
      x.append(1)
      return x
  ```

  - 根因：`f.__defaults__` 里存着那个列表对象，每次调用没传参就用它。
  - 同类坑：默认参数写成函数调用结果（`def f(t=datetime.now())`——时间被冻结在定义时刻）。
  - 检测手段：ruff 规则 B006 会在 CI 直接拦下。
- **记忆技巧：** 类比——默认参数是函数的"**婚前财产**"：领证（def）那一刻就定好了，之后每段婚姻（每次调用）用的都是同一套房。
- **面试官追问：**
  1. *不可变默认参数（如 `x=0`）为什么安全？* → 无法原地改，重新赋值只影响局部标签。
  2. *想让默认是"调用时刻"的时间怎么办？* → 默认 None，体内 `t = t or datetime.now()`（注意 falsy 边界，更严谨用 `if t is None`）。
  3. *Pydantic 模型里字段默认 [] 也有同样问题吗？* → 没有：Pydantic v2 对 `Field(default_factory=list)` 或默认 `[]` 都会为每个实例复制——但普通 Python 函数没有这个保护。
- **项目关联：** 云合 DTO 层统一用 `x: str | None = Field(default=None, ...)` 的 None 哨兵模式（如 `application/dto/request/chat.py` 的 `user_id` / `agent_id`），与 Python 层"默认 None"约定一脉相承；ruff 在 CI 阻断式执行（AGENTS.md §6），B 类规则让这类陷阱在提交前失败。

---

#### 【面试题 9】闭包是什么？装饰器的原理？手写一个。

- **难度：** ⭐⭐⭐
- **一句话答案：** 闭包 = 内层函数引用了外层函数的局部变量，且外层返回内层后这些变量仍然存活的"函数 + 出生环境"组合。装饰器本质是 `f = decorator(f)` 的语法糖：接收函数、返回包装函数的可调用对象。
- **考察点：** 作用域链、自由变量、装饰器堆叠顺序、`functools.wraps`——这是 Python 中级分水岭。
- **参考答案：**

  ```python
  import functools
  import time

  def retry(times: int):
      """带参数的装饰器：三层嵌套。"""
      def decorator(func):
          @functools.wraps(func)          # 保留 __name__/__doc__
          def wrapper(*args, **kwargs):
              for attempt in range(1, times + 1):
                  try:
                      return func(*args, **kwargs)
                  except Exception:
                      if attempt == times:
                          raise
          return wrapper
      return decorator

  @retry(times=3)                          # 等价于 f = retry(3)(f)
  def call_llm() -> str: ...
  ```

  - 闭包三要素：嵌套函数 + 引用外层变量（自由变量）+ 外层返回内层。
  - 装饰器执行时机：**导入/定义时**就完成包装，调用时执行的是 wrapper。
  - 多个装饰器堆叠：从下往上包装，从上往下执行。
  - 类装饰器实现 `__call__` 即可；`functools.wraps` 解决元信息丢失。
- **记忆技巧：** 类比——装饰器是"**包装纸**"：礼物（原函数）不变，外面套一层纸（增强功能），`@wraps` 是在纸上贴回原标签。口诀——"**定义时包装，调用时增强；多层装饰，下穿上调**"。
- **面试官追问：**
  1. *装饰器为什么要三层嵌套（带参时）？* → 最外层收装饰器参数，中间收函数，最内层收调用参数。
  2. *装饰器里修改 `*args` 再透传算破坏封装吗？* → 属于"拦截器"模式，AOP 常用（鉴权、日志），但要保证对调用方透明。
  3. *异步函数的装饰器注意什么？* → wrapper 也要是 `async def`，否则 await 语义丢失。
- **项目关联：** FastAPI 路由装饰器（`api/v1/chat.py` 等模块顶部的 `@router.post(...)`）就是带参装饰器的教科书用法：定义期完成注册，运行期按注册表分发——面试时可自然衔接到第 04 章。

---

#### 【面试题 10】lambda、map/filter 和 functools 常用工具？

- **难度：** ⭐
- **一句话答案：** lambda 是单表达式匿名函数，适合一次性小逻辑；多数场景推导式比 map/filter 更可读。functools 高频四件套：`lru_cache`（记忆化）、`partial`（参数预绑）、`reduce`（折叠）、`wraps`（保元信息）。
- **考察点：** 函数式工具的分寸感——知道何时用、何时不用。
- **参考答案：**
  - lambda 限制：只能一个表达式，不能写语句/注解；复杂逻辑请用 def。
  - `functools.lru_cache(maxsize=128)`：以参数为 key 缓存返回值，要求参数可哈希；注意缓存可变结果会共享引用、缓存实例方法会持有 self 造成泄漏。
  - `partial(func, fixed_arg)`：生成"预填参数"的新可调用对象，回调装配常用。
  - `sorted(key=lambda x: x.score, reverse=True)` 是 lambda 最正当的用法。
- **记忆技巧：** 口诀——"**lambda 一次性，排序 key 最相宜；map filter 不如推导，缓存偏函数靠 functools**"。
- **面试官追问：**
  1. *lambda 闭包捕获循环变量的坑？* → 延迟绑定：`[lambda: i for i in range(3)]` 全部返回 2；修法 `lambda i=i: i`（用默认参数当场定值——恰好是 Q8 陷阱的正向利用）。
  2. *lru_cache 用在 LLM 调用上合适吗？* → 可以缓存确定性请求，但要小心 key 里含长 prompt 的内存占用与命中率；生产上更常用带 TTL 的外部缓存。
  3. *reduce 为什么被"打入冷宫"？* → 可读性差，显式循环更清晰；Python 3 把它移进 functools 就是这个态度。
- **项目关联：** 云合调度器 `application/scheduler.py` 用 `asyncio.to_thread(distiller.run_distillation, uid)` 把"函数 + 参数"传给线程执行——这正是 partial 思想的变体；面试可一句话带出"同步函数异步入线程池"的桥接模式（第 03 章展开）。

---

## 第三层 · 迭代与资源管理（Q11~Q13）

---

#### 【面试题 11】可迭代对象与迭代器的区别？

- **难度：** ⭐⭐
- **一句话答案：** 可迭代对象实现了 `__iter__`（能给你迭代器）；迭代器实现了 `__iter__`（返回自己）和 `__next__`（给出下一个元素，耗尽抛 `StopIteration`）。`for` 循环就是"先 `iter()` 拿迭代器，再反复 `next()` 直到 StopIteration"的语法糖。
- **考察点：** 迭代协议是否真正理解；能否区分"能被 for 的"和"被 for 时实际干活的"。
- **参考答案：**

  ```python
  class Counter:
      """迭代器：自带状态，只能消费一次。"""
      def __init__(self, n: int) -> None:
          self._n, self._i = n, 0

      def __iter__(self):  # 迭代器的 __iter__ 返回自己
          return self

      def __next__(self) -> int:
          if self._i >= self._n:
              raise StopIteration
          self._i += 1
          return self._i
  ```

  - 关键差异：**可迭代对象可反复遍历（每次给新迭代器），迭代器是一次性的**（自带游标，耗尽即废）。这就是 `list` 能 for 两遍、`iter(list)` 只能 for 一遍的原因。
  - `iter()` 还能两参形式：`iter(callable, sentinel)`，反复调用直到返回哨兵值。
- **记忆技巧：** 类比——可迭代对象是**唱片**（可反复播放），迭代器是**唱针**（从头走到尾，走完就停）。口诀："**能 iter 的叫可迭代，有 next 的才是迭代器**"。
- **面试官追问：**
  1. *为什么 for 循环不会死循环在 StopIteration？* → for 内部捕获该异常并正常结束循环。
  2. *list 是迭代器吗？* → 不是，它只有 `__iter__`；`iter([1,2])` 返回的才是。
  3. *文件对象是可迭代还是迭代器？* → 是迭代器（逐行惰性读），所以大文件 `for line in f` 省内存。
- **项目关联：** 云合 SSE 聊天流（`api/v1/chat.py` 的异步生成器函数）就是"一次性迭代器"：每个请求拿到独立的事件流游标，消费完即结束——与 FastAPI `StreamingResponse` 的协议完全对齐。

---

#### 【面试题 12】生成器是什么？`yield` 的执行原理？为什么省内存？

- **难度：** ⭐⭐⭐
- **一句话答案：** 含 `yield` 的函数调用后返回生成器对象，函数体并不执行；每次 `next()` 才跑到下一个 `yield` 处**暂停并交出值**，状态（局部变量、指令位置）被完整保存。省内存是因为它惰性求值、一次只物化一个元素，内存 O(1)。
- **考察点：** 协程式"暂停/恢复"语义是否吃透；`send`/`throw`/`close` 了解程度。
- **参考答案：**

  ```python
  def stream_events():
      for i in range(3):
          yield f"data: event-{i}\n\n"   # 每次暂停在这里，下次从此恢复

  g = stream_events()   # 函数体一行都没跑
  next(g)               # 跑到第一个 yield，返回 "data: event-0\n\n"
  ```

  - 原理：生成器是有状态的"半协程"——`next` 恢复执行，`yield` 挂起；局部状态存在生成器对象的帧里。
  - 进阶 API：`gen.send(x)` 把值送进 `yield` 表达式；`throw` 注入异常；`close` 收尾（触发 GeneratorExit，走 finally 清理）。
  - `yield from sub_gen` 委托给子生成器，是 asyncio 早期协程实现的历史基础。
  - 与列表对比：列表是"全部造好再给你"，生成器是"要一个造一个"——处理流式/大文件/无限序列的唯一选择。
- **记忆技巧：** 类比——生成器是**自动售货机**：按一次（next）掉一瓶（yield），机器（状态）一直在；列表是一次性搬来一整箱。
- **面试官追问：**
  1. *生成器能 return 吗？* → 能，`return value` 会塞进 StopIteration.value；`yield from` 可接到它。
  2. *async 生成器是什么？* → `async def` + `yield`，用 `async for` 消费——SSE/WebSocket 流式响应的标准形态。
  3. *生成器为什么能表达无限流？* → 惰性求值无终止条件也安全，内存恒定。
- **项目关联：** 云合聊天接口正是 async 生成器流：`api/v1/chat.py` 中事件（含新闻证据卡片事件 `_build_evidence_event`）逐个 `yield` 成 `data: {...}\n\n` 帧推给前端，LLM 边产出、服务端边转发、前端边渲染——三段流水都靠生成器语义支撑。

---

#### 【面试题 13】`with` 语句原理？如何自定义上下文管理器？

- **难度：** ⭐⭐
- **一句话答案：** `with` 调用对象的 `__enter__`（返回值绑定 as 变量），退出时无论是否异常都调 `__exit__`；`__exit__` 返回 True 可吞掉异常。本质是 try/finally 的协议化，保证资源（文件、锁、连接、事务）必被释放。
- **考察点：** 资源管理意识；`__exit__` 三参数（异常类型/值/回溯）与返回值语义。
- **参考答案：**

  ```python
  from contextlib import contextmanager

  @contextmanager
  def timer(name: str):
      start = time.perf_counter()
      try:
          yield                     # with 体在这里执行
      finally:
          print(f"{name}: {time.perf_counter() - start:.3f}s")

  with timer("fetch"):
      do_something()
  ```

  - 类实现版：`__enter__` / `__exit__(self, exc_type, exc_val, exc_tb)`。
  - `contextlib` 还有：`closing`（包一层保证 close）、`suppress`（吞指定异常）、`ExitStack`（动态管理多个上下文）、`asynccontextmanager`（异步版）。
  - 典型应用：文件、锁、数据库事务、临时改配置、计时、测试 patch。
- **记忆技巧：** 口诀——"**进场 enter 拿资源，退场 exit 必清理；异常三参进 exit，True 吞下 False 扬**"。
- **面试官追问：**
  1. *`__exit__` 返回 True 的后果？* → 异常被吞，with 外完全无感——调试灾难，除非明确设计（如 suppress）。
  2. *嵌套 with 的清理顺序？* → 后进先出（栈序），与 ExitStack 一致。
  3. *sqlite3 连接对象当上下文管理器用时提交还是回滚？* → Python 的 `with conn:` 管理的是**事务**（正常提交、异常回滚），**不关闭连接**——关闭要另行 close，这是常见误用点。
- **项目关联：** 云合持久层 `infrastructure/persistence/connection.py` 的 `get_connection()` 采用线程本地（threading.local）缓存 + 活性探测（`SELECT 1`）复用连接，并配 `check_same_thread=False`——正是围绕 SQLite 连接生命周期做精细资源管理的实例；面试可顺势讲"SQLite 在 asyncio 服务里的连接策略"（第 12 篇深挖展开）。

---

## 第四层 · 面向对象（Q14~Q20）

---

#### 【面试题 14】类属性与实例属性的区别？查找顺序？

- **难度：** ⭐⭐
- **一句话答案：** 类属性存在类的 `__dict__`、被所有实例共享；实例属性存在实例自己的 `__dict__`。读取时先查实例、再查类、再沿 MRO 向上；写 `self.x = v` 永远写到实例上——若类属性是可变对象（如 list），"共享 + 原地改"就是经典事故。
- **考察点：** 属性查找链（MRO 前置版）；可变类属性坑。
- **参考答案：**

  ```python
  class Agent:
      kind = "base"            # 类属性：全类共享
      tools: list[str] = []    # 危险：可变类属性被所有实例共享！

      def __init__(self, name: str) -> None:
          self.name = name     # 实例属性：各自独立
  ```

  - 查找顺序：实例 `__dict__` → 类 `__dict__` → 父类（MRO 链）→ 找不到走 `__getattr__` / 抛 AttributeError。
  - `self.kind = "x"` 不会改类属性，而是在实例上创建同名属性"遮住"它。
  - 类属性的正当用途：全类共享的常量/配置、实例计数。
- **记忆技巧：** 类比——类属性是**教室黑板**（全班共用），实例属性是**个人笔记本**；你往笔记本抄一遍黑板内容，黑板并没变，但你看自己的本子就先看到抄的。
- **面试官追问：**
  1. *为什么可变类属性危险？* → `a.tools.append(...)` 会影响所有实例；要么放 `__init__` 里建实例属性，要么类属性只用不可变对象。
  2. *`__slots__` 是什么？* → 禁掉实例 `__dict__`，属性固定、省内存；代价是不能动态加属性、多重继承受限。
  3. *类方法里能改类属性吗？* → 能，`cls.attr = v` 改的就是全类共享的那份。
- **项目关联：** 云合 `domain/agent/base.py` 的 Agent 基类把"name/description 等元信息"做成 `@property` 由子类提供——用类级声明承载元信息、用实例状态承载运行数据，是"类属性 vs 实例属性"分工的生产写法。

---

#### 【面试题 15】`__init__` 和 `__new__` 的区别？

- **难度：** ⭐⭐⭐
- **一句话答案：** `__new__` 是构造器：负责**创建并返回**实例（分配内存），是静态方法特例；`__init__` 是初始化器：拿到已存在的实例填充状态，无返回值。日常 99% 只写 `__init__`；`__new__` 用于单例、不可变类型定制、工厂返回缓存实例等场景。
- **考察点：** 对象创建两阶段模型；`__new__` 返回其他对象时的行为。
- **参考答案：**

  ```python
  class Singleton:
      _instance: "Singleton | None" = None

      def __new__(cls) -> "Singleton":
          if cls._instance is None:
              cls._instance = super().__new__(cls)
          return cls._instance
  ```

  - 调用顺序：`cls(...)` → `__new__(cls, ...)` 返回 obj → 若 obj 是 cls 实例则 `obj.__init__(...)`。
  - 若 `__new__` 返回的不是本类实例，`__init__` 不会执行。
  - 继承不可变类型（str/tuple/int）要改内容必须在 `__new__` 阶段动手——实例造出来就改不了了。
- **记忆技巧：** 类比——`__new__` 是**盖楼**（把毛坯造出来），`__init__` 是**装修**（往里面摆家具）；毛坯都没有，装修无从谈起。
- **面试官追问：**
  1. *为什么继承 tuple 要重写 __new__？* → tuple 不可变，`__init__` 时内容已定型，只能在 `__new__` 里构造。
  2. *单例除了 __new__ 还有什么实现？* → 模块级对象（Python 最朴素可靠的单例）、元类、装饰器。
  3. *dataclass 和 __new__ 的关系？* → dataclass 生成的是 `__init__`（及 `__repr__`/`__eq__`），不碰 `__new__`。
- **项目关联：** 云合倾向用"组合根单例"而非 `__new__` 单例：`app.py` 的 `build_container(settings)` 在应用启动时创建唯一 `AppContainer` 并注入各处（AGENTS.md §8.2）——这是比语言级单例更可控、可测的架构级单例，面试时主动对比很加分。

---

#### 【面试题 16】`__str__` 和 `__repr__` 的区别？

- **难度：** ⭐
- **一句话答案：** `__str__` 面向**用户**（print/str()，可读性优先）；`__repr__` 面向**开发者**（解释器回显、日志、调试，要求无歧义，理想情况 `eval(repr(x))` 能重建对象）。只实现一个时优先 `__repr__`——`__str__` 缺省会回退到 `__repr__`。
- **考察点：** 双受众意识；dataclass 自动生成 repr 的工程价值。
- **参考答案：**

  ```python
  from dataclasses import dataclass

  @dataclass
  class StockSignal:
      code: str
      score: float
      # dataclass 自动生成：
      # __repr__ -> StockSignal(code='600519', score=87.5)

  print(StockSignal("600519", 87.5))   # __str__ 缺省 → 回退用 __repr__
  ```

  - 容器打印元素时用的是元素的 `__repr__`（即使容器走 str）。
  - 日志里永远用 repr 语义（`%r` / f-string `!r`），避免空字符串/不可见字符带来的误判。
- **记忆技巧：** 口诀——"**str 给用户看脸，repr 给程序员看骨；日志要用 repr，ambiguit 无处藏**"（简化记："脸用 str，骨用 repr"）。
- **面试官追问：**
  1. *f"{obj!r}" 是什么意思？* → 强制用 `__repr__` 格式化。
  2. *dataclass 的 repr 怎么定制？* → `field(repr=False)` 排除敏感字段（如 token）——防泄漏进日志。
  3. *为什么 __repr__ 最好无歧义？* → 调试/日志场景要能精确定位对象内容，"Object at 0x..." 毫无意义。
- **项目关联：** 云合全库用 dataclass 承载领域值（`domain/shared/llm/ports.py` 的 `LLMRequest` / `LLMResponse` 等），免费获得可读 repr；同时 AGENTS.md §4 规定敏感信息不得进日志——与 `field(repr=False)` 是同一安全思想。

---

#### 【面试题 17】`__eq__` 和 `__hash__` 有什么约定？

- **难度：** ⭐⭐⭐
- **一句话答案：** 约定：**`a == b` 为真，必须有 `hash(a) == hash(b)`**（反向不要求）。自定义 `__eq__` 而不定义 `__hash__` 时，Python 会把 `__hash__` 置为 None——对象变得不可哈希，不能直接当 dict key / 进 set。
- **考察点：** 哈希表一致性原理；可变对象做 key 的事故机理。
- **参考答案：**
  - 默认行为：`object` 的 `__eq__` 是身份比较、`__hash__` 基于 `id()`——天然满足约定。
  - 值相等即哈希相等的实现要点：hash 只由"参与 eq 比较的字段"计算，且这些字段本身不可变。
  - 可变对象若按值实现 eq，放进 dict 后字段被改 → 哈希值漂移 → key"丢失"（找不回来也删不掉），这是经典线上事故。
  - 解法：用 `@dataclass(frozen=True, eq=True)` 自动生成一致的 eq/hash；或明确 `eq=False` 退回身份语义。
- **记忆技巧：** 口诀——"**eq 同则 hash 同，eq 改 hash 封；可变不做 key，frozen 保平安**"。
- **面试官追问：**
  1. *哈希冲突会怎样？* → 哈希表再按 `==` 逐个比较，正确性不受影响、性能退化。
  2. *为什么 tuple 可做 key 而 list 不行？* → tuple 定义了基于内容的 hash（且不可变）；list 不可哈希（`__hash__ = None`）。
  3. *dataclass 默认 eq=True 时 hash 是什么？* → 非 frozen 时 `__hash__` 置 None（遵循"可变不哈希"）；frozen + eq 才自动生成 hash。
- **项目关联：** 云合 `domain/academic/context.py` 使用 `@dataclass(frozen=True)` 正是这套约定的落地：frozen 实例可哈希、可安全作缓存键与集合元素，跨层传递不怕被改。

---

#### 【面试题 18】继承、MRO 和 `super()` 的本质？

- **难度：** ⭐⭐⭐
- **一句话答案：** 多重继承下方法查找顺序由 C3 线性化算法决定（可用 `Cls.__mro__` 查看）；`super()` 不是"父类"，而是"**按 MRO 链的下一个类**"——这让菱形继承中每个类的方法恰好执行一次（协作式多继承）。
- **考察点：** 菱形继承问题；为什么说 `super()` 语义常被误解。
- **参考答案：**

  ```python
  class A:
      def who(self) -> str:
          return "A"

  class B(A):
      def who(self) -> str:
          return "B→" + super().who()

  class C(A):
      def who(self) -> str:
          return "C→" + super().who()

  class D(B, C):
      pass

  D().who()        # "B→C→A"：按 MRO 依次接力，A 只跑一次
  D.__mro__        # D, B, C, A, object
  ```

  - C3 规则：局部优先（子类先于父类）+ 单调性（保持各父类声明顺序）。
  - 协作式继承约定：每个类都调 `super().__init__(*args, **kwargs)`，让链上每一环都有机会初始化。
  - 组合优于继承：层级超过两层就该警惕；Python 还有 Mixin 模式（小而专一的功能类）。
- **记忆技巧：** 口诀——"**super 不是爹，是排队下一个；MRO 用 C3，菱形只跑一遍**"。
- **面试官追问：**
  1. *菱形继承的祖先初始化两次怎么避免？* → 全员协作式 super + 公共祖先的 `__init__` 幂等/只做一次。
  2. *super() 无参为什么能工作？* → 编译器在类体内自动注入 `__class__` 单元格，等价 `super(__class__, self)`。
  3. *Mixin 和 ABC 怎么选？* → Mixin 提供实现复用（可实例化语义弱）；ABC 定义契约（`@abstractmethod` 强制子类实现）。
- **项目关联：** 云合 Agent 体系以 `domain/agent/base.py` 为基类、`dynamic_agent.py` 等扩展——层级刻意保持浅（基类定契约、子类补行为），与"组合优于继承"原则一致；更复杂的差异通过编排层（`orchestrator.py`）组合实现，而非堆继承。

---

#### 【面试题 19】`@staticmethod` / `@classmethod` / `@property` 的区别？

- **难度：** ⭐⭐
- **一句话答案：** `staticmethod` 不收隐式参数，是挂在类上的普通函数（逻辑归属）；`classmethod` 收 `cls`，常用于**备选构造器**（`from_dict` 这类工厂）；`property` 把方法伪装成属性访问，用于受控读写/惰性计算。
- **考察点：** 三者绑定机制差异；各自的"正当用途"而非滥用。
- **参考答案：**

  ```python
  class Token:
      def __init__(self, value: str) -> None:
          self._value = value

      @property
      def masked(self) -> str:          # 读作属性，实为方法
          return self._value[:4] + "***"

      @classmethod
      def from_header(cls, header: str) -> "Token":   # 备选构造器
          return cls(header.removeprefix("Bearer "))

      @staticmethod
      def is_well_formed(value: str) -> bool:         # 纯逻辑，不碰实例/类
          return len(value) > 10
  ```

  - 绑定差异：实例调 staticmethod 不传 self；classmethod 无论类调还是实例调都拿到 cls（子类调用时 cls 是子类——工厂天然支持多态）。
  - property 进阶：`@x.setter` / `@x.deleter` 做校验与缓存失效；只读暴露内部状态的标准手段。
- **记忆技巧：** 口诀——"**static 是借住的工具人，classmethod 是工厂厂长（认 cls 这个厂牌），property 是化妆成属性的方法**"。
- **面试官追问：**
  1. *classmethod 工厂比直接 __init__ 重载好在哪？* → 语义命名（`from_header`/`from_dict`）、子类继承时返回正确类型。
  2. *property 什么时候反模式？* → 访问有重 IO/明显副作用时——属性访问应廉价，昂贵操作用方法。
  3. *怎么实现"可写但带校验"的属性？* → `@x.setter` 里做校验，非法值抛异常。
- **项目关联：** 全部三类在云合均有真实用法：`domain/travel/itinerary/schema.py` 用一组 `@classmethod` 做行程 schema 的构造/反序列化工厂；`domain/safety/prompt_guard.py` 用 `@staticmethod` 承载纯校验逻辑；`domain/agent/base.py`、`domain/agent/orchestrator.py` 用 `@property` 暴露只读元信息。

---

#### 【面试题 20】鸭子类型是什么？dataclass 解决了什么问题？

- **难度：** ⭐⭐
- **一句话答案：** 鸭子类型 = "叫得像鸭子、游得像鸭子，那就是鸭子"——只关心对象**有没有需要的方法/属性**，不关心它的类。dataclass 用一行装饰器自动生成 `__init__`/`__repr__`/`__eq__`，消灭纯数据类的样板代码。
- **考察点：** Python 多态观（协议优于继承）；dataclass 常用参数。
- **参考答案：**
  - 鸭子类型配套工具：`hasattr` 探测、ABC 注册、`typing.Protocol`（Q25，把鸭子类型**静态化**）。
  - dataclass 高频参数：`frozen=True`（不可变+可哈希）、`slots=True`（省内存）、`kw_only=True`（强制关键字传参）、`field(default_factory=list)`（安全默认值）、`field(repr=False)`（敏感字段不进 repr）。
  - dataclass vs NamedTuple vs Pydantic：dataclass 是通用值对象；NamedTuple 更轻且不可变；Pydantic 带**运行时校验**，用于边界（API 入参）——云合的划分是"边界用 Pydantic DTO，领域内部用 dataclass"。
- **记忆技巧：** 口诀——"**不看血统看本领（鸭子类型）；样板代码全免单（dataclass）**"。
- **面试官追问：**
  1. *鸭子类型的风险？* → 拼写错误/接口漂移只能在运行期暴露——大型项目用 Protocol + mypy 把它拉回编译期。
  2. *dataclass 可变默认字段怎么写？* → `field(default_factory=list)`，直接写 `= []` 会被拒绝（dataclass 替你挡下了 Q8 的坑）。
  3. *frozen dataclass 还能改吗？* → 不能原地改，但可 `dataclasses.replace(obj, x=1)` 生成新实例（不可变更新）。
- **项目关联：** 云合领域层 dataclass 多达 40+ 处（`domain/agent/orchestrator.py`、`domain/shared/tools/base.py`、`domain/travel/itinerary/schema.py` 等），与 Pydantic DTO（`application/dto/`）形成"内 dataclass、外 Pydantic"的清晰分工——这是面试讲"分层数据载体选型"的现成素材。

---

## 第五层 · 异常处理（Q21~Q23）

---

#### 【面试题 21】try / except / else / finally 的执行顺序？

- **难度：** ⭐
- **一句话答案：** try 无异常 → 跳过 except、执行 else，最后必走 finally；try 有异常 → 按顺序匹配第一个能接住的 except，跳过 else，必走 finally。`else` 的意义：把"成功后才做的事"与"被保护的代码"分开，缩小异常捕获范围。
- **考察点：** else 的存在价值；finally 与 return 的交互。
- **参考答案：**

  ```python
  def load() -> str:
      try:
          data = read()          # 只保护可能抛错的最小区间
      except FileNotFoundError:
          return "missing"
      else:
          return parse(data)     # 只有 read 成功才执行；parse 抛错不被上面 except 误吞
      finally:
          close()                # 无论何种路径都执行（含 return 之前）
  ```

  - finally 在 return 之前执行；finally 里再 return 会**吞掉异常和原返回值**——禁止写法。
  - except 匹配顺序：子类在前父类在后，否则子类分支永远不可达。
- **记忆技巧：** 口诀——"**无错走 else，有错找 except，天塌下来 finally**"。
- **面试官追问：**
  1. *finally 里 return 会发生什么？* → 覆盖 try 里的返回值/异常，bug 黑洞，lint 会拦。
  2. *多个 except 合并写法？* → `except (KeyError, ValueError) as e:`。
  3. *except* 顺序写反（父类在前）会怎样？* → 子类分支死代码；部分 linter 能查出。
- **项目关联：** 云合 `api/middleware/error_handler.py` 把"领域异常 → HTTP 响应"的翻译收口在统一中间件——路由内只写最小 try 区间，与"缩小捕获范围"的 else 哲学一致。

---

#### 【面试题 22】为什么不能写裸 `except:`？异常链 `raise ... from ...` 是什么？

- **难度：** ⭐⭐
- **一句话答案：** 裸 `except:` 会接住**一切**，包括 `KeyboardInterrupt`、`SystemExit`，让程序"关不掉、错不了、查不出"——错误被吞，bug 变灵异事件。`raise NewError(...) from e` 显式保留原始异常链，日志里能看到完整因果（`__cause__`）。
- **考察点：** 异常层次结构（BaseException vs Exception）；可观测性意识。
- **参考答案：**
  - 异常层次：`BaseException` → `Exception` → 具体异常；`KeyboardInterrupt`/`SystemExit`/`GeneratorExit` 直接挂在 BaseException 下，**不属于 Exception**——所以底线是 `except Exception:`，且仍要慎用于具体场景。
  - 正确姿势：捕获**具体**异常 + 保留链：

    ```python
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DecisionParseError("LLM 决策 JSON 解析失败") from e
    ```

  - `from e` 显式链（__cause__）；不写 from 在 except 内 raise 也会带隐式上下文（__context__）；`from None` 则主动切断。
  - 吞异常三宗罪：掩盖 bug、破坏中断语义、让监控失明。真要兜底，记录日志并带上下文字段，再决定重抛或降级。
- **记忆技巧：** 口诀——"**裸 except 是黑洞，具体异常才下手；raise from 留案底，排障不抓瞎**"。
- **面试官追问：**
  1. *`except Exception` 就安全了吗？* → 比裸的好，但范围仍过大；理想是精确到具体类型，且 except 体不做会再抛错的事。
  2. *异步任务里吞异常有什么特殊危害？* → `asyncio.create_task` 的异常若无人 await/取 result，只在 GC 时打印 "Task exception was never retrieved"——静默失败。
  3. *什么时候允许广捕获？* → 进程/请求最外层的兜底（转 500 + 记日志）、隔离不可信插件——并且必须记日志。
- **项目关联：** 这是云合的明文红线：AGENTS.md §5 要求"捕获具体异常并保留异常链；禁止裸 except、吞异常和向客户端暴露堆栈"；应用层配套了分层异常体系（见 Q23），ruff + CI 阻断执行让规范可落地而非口号。

---

#### 【面试题 23】如何设计自定义异常体系？

- **难度：** ⭐⭐⭐
- **一句话答案：** 三原则：**单一基类**收口（便于上层一把接）、**按业务域分层**（NotFound/Conflict/Validation/RateLimit/Internal…语义化命名）、**在系统边界统一翻译**成对外协议（HTTP 状态码/错误码），堆栈与敏感细节留在服务端日志。
- **考察点：** 异常是 API 设计的一部分——考察你"错误契约"的设计能力。
- **参考答案：**

  ```python
  class AppError(Exception):
      """应用异常基类：携带对外的错误码与安全文案。"""

  class NotFoundError(AppError):
      """资源不存在或无权访问（对外统一 404，不暴露存在性）。"""

  class ConflictError(AppError):
      """状态冲突（如重复提交/幂等冲突，对外 409）。"""
  ```

  - 语义化好处：上层 `except NotFoundError` 精确；中间件按类型映射状态码。
  - 跨用户访问返回 404 而非 403 的安全设计：不暴露资源存在性（防枚举）。
  - 异常里放"可对外说的文案"和"只对日志说的细节"两份信息，边界处只出前者。
- **记忆技巧：** 口诀——"**一个基类管全家，按域分家语义化，边界统一做翻译，敏感细节不出门**"。
- **面试官追问：**
  1. *为什么不用内置 ValueError 一把梭？* → 语义丢失：调用方无法区分"参数格式错"与"业务冲突"，上层翻译只能猜。
  2. *异常和错误码返回怎么选？* → 进程内用异常（不污染正常返回路径），进程间用错误码（HTTP/RPC 契约）。
  3. *第三方库的异常怎么处理？* → 在适配层包装成自家异常（带 from 链），不让 SQLite/HTTP 异常泄漏到领域层——这正是端口隔离的收益。
- **项目关联：** 云合的体系就是标准答案：`application/exceptions/` 按 `base/auth/not_found/conflict/validation/rate_limit/internal` 8 个模块分层，由 `api/middleware/error_handler.py` 统一翻译为响应；其中"对象级未授权统一 404"（AGENTS.md §4）直接体现了上面的防枚举设计。

---

## 第六层 · 类型系统（Q24~Q25）

---

#### 【面试题 24】类型注解的价值？`X | None` 和 `Optional[X]` 的区别？

- **难度：** ⭐⭐
- **一句话答案：** 注解不改运行行为，价值在于**静态检查（mypy）+ IDE 补全 + 文档化 + FastAPI/Pydantic 的运行时校验入口**。`X | None`（3.10+）与 `Optional[X]` 语义等价，前者更短、与现代内置泛型（`list[int]`）风格统一，新项目首选。
- **考察点：** 是否理解"渐进式类型"的定位；注解生态如何转化为工程收益。
- **参考答案：**
  - 运行期注解只是元数据（`__annotations__`），解释器不校验——但 Pydantic/FastAPI 会**消费注解做运行时校验**，这是 FastAPI 生态的地基。
  - 配套能力：`from __future__ import annotations` 延迟求值；mypy 严格模式在 CI 阻断——注解从"建议"变"门禁"。
  - 收益量化话术：重构时 mypy 能把"改一处签名波及全库"的错误在提交前列出，相当于免费的回归测试网。
- **记忆技巧：** 口诀——"**注解三收益：静态查、IDE 懂、框架用；竖线 None 新写法，门禁一开变合同**"。
- **面试官追问：**
  1. *`Optional[X]` 和 `X | None = None` 一样吗？* → 语义同；注意 `= None` 是给默认值，与类型标注是两回事。
  2. *运行期能强制校验注解吗？* → 标准库不管；用 Pydantic / beartype / typeguard 可强制。
  3. *`Any` 滥用的后果？* → 类型系统信任崩塌，mypy 静默放行——项目应禁裸 Any 或显式申报。
- **项目关联：** 云合把注解变成硬约束：`application/dto/request/travel.py` 等统一 `title: str | None = Field(...)` 风格；`python -m mypy api application domain infrastructure` 是 CI 阻断关卡（AGENTS.md §6）；前端同样 TypeScript strict 禁 any——"类型即合同"是全栈一致的工程文化。

---

#### 【面试题 25】Python 泛型怎么用？`Protocol` 是什么？

- **难度：** ⭐⭐⭐（通往架构篇的桥梁题）
- **一句话答案：** 泛型用 `list[T]` / `dict[K, V]` / `TypeVar` 表达"类型参数化"，让容器和函数在保持类型安全的前提下复用。`Protocol` 是**结构化类型**：定义一组方法签名，任何实现了这些方法的类都自动兼容——不需要显式继承，即"静态化的鸭子类型"。
- **考察点：** Protocol vs ABC 的取舍；这是理解"端口与适配器"架构（依赖倒置）的语言基础。
- **参考答案：**

  ```python
  from typing import Protocol

  class LLMPort(Protocol):
      """领域层只声明"我需要什么能力"，不关心谁来实现。"""
      async def complete(self, request: LLMRequest) -> LLMResponse: ...

  class OpenAILLM:                       # 不继承 LLMPort
      async def complete(self, request: LLMRequest) -> LLMResponse:
          ...                            # 结构匹配即兼容，mypy 通过
  ```

  - Protocol vs ABC：ABC 是"**名义**子类型"（必须继承，强调 is-a 血缘）；Protocol 是"**结构**子类型"（方法对上就行，强调 can-do 能力）。依赖外部库对象/解耦场景用 Protocol；要强制契约+提供公共实现用 ABC。
  - `runtime_checkable` 装饰后可用 `isinstance` 检查（仅检查方法存在，不查签名）。
  - 工程闭环：领域定义 Protocol 端口 → 基础设施写实现（不必 import 端口也能对上）→ 组合根注入 → 测试给 fake 实现——依赖倒置就这样落到代码。
- **记忆技巧：** 口诀——"**ABC 认血统，Protocol 认本领；端口定在领域里，实现随便换**"。
- **面试官追问：**
  1. *Protocol 的方法签名不完全一致会怎样？* → mypy 报错；运行期不拦——所以 Protocol 价值在静态侧，配套 mypy 门禁才有意义。
  2. *TypeVar 协变/逆变是什么？* → `list[Cat]` 不是 `list[Animal]`（不变）；只读容器可协变（`Sequence[Cat]` ⊆ `Sequence[Animal]`），只写位置逆变——记"生产者协变、消费者逆变"（PECS）。
  3. *为什么端口 Protocol 不该照抄实现类的全部公开方法？* → 端口要按**消费方需求**最小化定义，否则泄漏装配细节、fake 实现成本爆炸——这是端口设计的核心纪律。
- **项目关联：** 云合全库 20+ 个 Protocol 端口：`domain/shared/llm/ports.py` 的 `LLMPort`、`domain/user/auth/ports.py` 的 `UserRepositoryPort`/`TokenRepositoryPort`/`PasswordHasherPort`、`domain/stock/ports.py` 的 `StockDataSource`、`domain/shared/mcp/ports.py` 的 `MCPCatalogPort` 等——AGENTS.md §8.1 规定"端口先于实现、按业务聚合命名、不得复制实现类全部公开方法"，是本题的标准项目叙事，并直接通向深挖篇第 10 篇。

---

## 本章速查表（面试前 30 分钟扫读）

| # | 题目 | 一句话答案 |
|---|---|---|
| 1 | 可变/不可变 | 数串组不可变、列典集可变；不可变的"改"是造新对象 |
| 2 | 四容器底层 | list 动态数组 / tuple 定长 / dict 哈希表(3.7+ 保序) / set 只有 key 的哈希表 |
| 3 | == vs is | == 比值走 __eq__，is 比身份走 id()；驻留是实现细节不可依赖；is 只用于 None 等单例 |
| 4 | 深浅拷贝 | 浅拷换壳不换芯、深拷整条对象图；赋值不是拷贝 |
| 5 | 切片/推导式 | 左闭右开负步反转；推导式声明式、惰性选生成器表达式 |
| 6 | 参数传递 | 按对象引用共享传递：原地改可见、重新绑定不可见 |
| 7 | *args/**kwargs | 一星收位置成 tuple、双星收关键字成 dict；顺序 普→星→键→双星 |
| 8 | 可变默认参数 | 默认值 def 时只求值一次被共享；一律默认 None 体内重建 |
| 9 | 闭包/装饰器 | 闭包=函数+出生环境；装饰器=f=deco(f)，定义时包装、@wraps 保元信息 |
| 10 | lambda/functools | lambda 一次性；四件套 lru_cache/partial/reduce/wraps |
| 11 | 迭代协议 | 可迭代有 __iter__、迭代器加 __next__；可迭代可反复、迭代器一次性 |
| 12 | 生成器 | yield 暂停存档、next 恢复；惰性 O(1) 内存；async 生成器是 SSE 基础 |
| 13 | with | __enter__/__exit__ 协议化 try/finally；exit 返 True 吞异常；with conn 管事务不管关闭 |
| 14 | 类/实例属性 | 类属性共享、实例属性私有；查找 实例→类→MRO；可变类属性是坑 |
| 15 | __new__/__init__ | new 盖楼返回实例、init 装修无返回；不可变类型改造在 new |
| 16 | __str__/__repr__ | str 给用户、repr 给开发者；日志用 repr；dataclass 白送 repr |
| 17 | eq/hash 约定 | eq 同则 hash 必同；自定义 eq 会封 hash；可变不做 key，frozen 保平安 |
| 18 | MRO/super | C3 线性化；super 是"MRO 下一个"不是"父类"；菱形只跑一遍 |
| 19 | static/class/property | 工具人 / 厂长(cls 工厂) / 化妆成属性的方法 |
| 20 | 鸭子类型/dataclass | 不看血统看本领；dataclass 免样板，边界用 Pydantic、内部用 dataclass |
| 21 | 异常四件套 | 无错 else、有错 except、必走 finally；finally 里禁 return |
| 22 | 裸 except/异常链 | 裸 except 吞一切含中断；底线 except Exception 且记日志；raise from 留链 |
| 23 | 异常体系 | 单基类+按域分层+边界统一翻译；跨用户访问用 404 防枚举 |
| 24 | 类型注解 | 静态查/IDE/框架三收益；X \| None 新风格；mypy 门禁变合同 |
| 25 | 泛型/Protocol | Protocol=结构化鸭子类型，认本领不认血统；端口先于实现→依赖倒置 |

---

## 自测清单（合上文档能复述）

- [ ] 三句话讲清"可变性"及其三个推论（dict key、线程安全、传参行为）
- [ ] 不看代码手写：重试装饰器（带参 + @wraps）
- [ ] 画出 D(B, C) 菱形继承的 MRO 并解释 super() 接力
- [ ] 默写可变默认参数陷阱的错误/正确两版写法，并说清根因（__defaults__）
- [ ] 说出生成器三种进阶 API（send/throw/close）及 async 生成器与 SSE 的关系
- [ ] 复述 eq/hash 约定 + "哈希漂移丢 key"事故机理
- [ ] 讲清云合异常体系：8 模块分层 → error_handler 统一翻译 → 404 防枚举
- [ ] 用 Protocol 定义一个端口并解释"ABC 认血统、Protocol 认本领"

---

## 项目关联代码核实记录

> 依据 `../README.md` 铁律 1/2/3，本章所有「项目关联」锚点已在写作前检索核实：

| 锚点 | 核实方式 |
|---|---|
| `application/dto/request/travel.py`、`chat.py` 的 `str \| None = Field(...)` 与 `ConfigDict(extra="forbid")` | 检索 `\| None = None`、`ConfigDict(extra="forbid")` 命中 |
| `domain/**/ports.py` 共 21 处 `class X(Protocol)`（含 `LLMPort`、`StockDataSource`、`PasswordHasherPort` 等） | 检索 `class \w+\(Protocol\)` 命中 21 处 |
| `@dataclass` 在 domain 下 44 处（含 `orchestrator.py`、`shared/llm/ports.py`）；`@dataclass(frozen=True)` 见 `domain/academic/context.py` | 检索 `@dataclass` 命中 |
| `@property`：`domain/agent/base.py`、`orchestrator.py`；`@classmethod`：`domain/travel/itinerary/schema.py`（7 处）；`@staticmethod`：`domain/safety/prompt_guard.py` | 检索装饰器命中 |
| `api/v1/chat.py` SSE 异步生成器（`yield _build_evidence_event(...)`、`yield f"data: {...}\n\n"`） | 检索 `yield ` 命中 |
| `asyncio.to_thread`：`application/scheduler.py`（蒸馏入线程）、`infrastructure/stock/stock_daily_fetcher.py`（akshare 桥接） | 检索 `asyncio.to_thread` 命中 35 处（含注释/测试） |
| 异常体系：`application/exceptions/` 8 模块 + `api/middleware/error_handler.py` | 目录列举核实 |
| `infrastructure/persistence/connection.py` 线程本地连接复用（`SELECT 1` 活性探测、`check_same_thread=False`） | 检索核实 |
| 规范类锚点：AGENTS.md §4（404 防枚举）、§5（禁裸 except/异常链）、§6（mypy/ruff 阻断）、§8.1（端口先于实现） | AGENTS.md 原文 |

> 注：全库未检出显式 `raise ... from` 用法——Q22 的项目叙事以"规范要求 + 异常体系 + 边界翻译"为准，不虚构代码实践（遵守铁律 7「不夸大」）。
