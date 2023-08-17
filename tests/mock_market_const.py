# 가상 시장에서 시장이 변화하는 간격
# 값이 0.1이면 0.1초마다 시장 정보가 변합니다.
MARKET_CHANGE_INTERVAL = 0.1

# 주가의 기본 단위
# 5이면 1405원, 1410원과 같이 주가가 5의 단위로 바뀝니다.
PRICE_UNIT = 5

# 주가의 최대 변화량
# 주가가 변할 때마다 최대 아래 값만큼 상승 및 하락이 이루어집니다.
MAX_PRICE_CHANGE = 50

# 호가의 최대 변화량
# 각 매수 매도 호가가 변할 때마다 최대 아래 값만큼 상승 및 하락이 이루어집니다.
MAX_ASK_BID_CHANGE = 10

# 주가의 시작 가격 범위
# 주가는 아래 튜플 사이의 랜덤한 값으로 정해집니다.
START_PRICE_RANGE = (1000, 2500)

# 주가의 최소 금액
# 주가는 이 가격 밑으로 떨어지지 않습니다.
MIN_PRICE = 1000

# 호가 수량의 시작 범위
# 호가 수량은 아래 튜플 사이의 랜덤한 값으로 정해집니다.
START_ASK_BID_RANGE = (0, 100)

# 시작 금액
START_DEPOSIT = 10000000