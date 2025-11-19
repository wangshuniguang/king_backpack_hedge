### 背包 backpack交易所做市策略 （记得加入我们战队：https://backpack.exchange/join/996）


#### 特别提示！！！
最新版本开源：https://github.com/wangshuniguang/ak47_backpack_market_maker/tree/master

该策略是完全接近真正的做市策略，并且经受了3~4亿交易量的实践考验，效果
非常的好，实际磨损无论极端行情都接近于1万交易量1U磨损，对于不少品种甚至
都能做到磨损万0.5U，强烈推荐！
****************************

当前程序是以简单的做市方式来在Backpack交易所交易，支持开启对冲，当前主要是使用lighter对冲。

可以不使用对冲模式运行，对冲程序和主做市程序是独立的。建议先忽略lighter对冲的king_of_hedge.py
先从简单的Backpack单交易所刷量开始。

配置的时候需要配置config/config.py中的backpack AK就
可以运行了。

主程序是market_maker.py，运行之前需要根据自己的需要
调整如下三个参数：
ticker、quantity、max_position_count，
其他的参数都不用调整。 这三个参数分别表示加密货币代号、单次
挂单买的数量、最大持有的数量。 这三个都很重要，刚开始运行的时候
一定要严格限定最大头寸！！！！！！

### 加入Backpack战队，享受更低手续费
https://backpack.exchange/join/996

一起为10万分目标而奋斗！！

### 联系我们
遇到任何问题可以TG或者推特上联系我们：
X账号：@dog_gold70695

TG账号：
![img_1.png](img_1.png)
