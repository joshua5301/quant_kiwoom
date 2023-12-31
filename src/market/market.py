from __future__ import annotations
import datetime
import logging
import time
import queue
from typing import *
from PyQt5.QtCore import QMutex, QMutexLocker

from .decorators import trace, order_api_method, request_api_method
from .kiwoom_api_utils import KiwoomAPIUtils
from .market_data import MarketData
from .client_signal_handler import ClientSignalHandler

logger = logging.getLogger(__name__)

class Market():
    """
    주식시장을 구현한 클래스
    
    Client는 이 클래스의 메서드를 통해 주식과 계좌 정보를 얻고 이를 바탕으로 매매할 수 있습니다.
    여러 쓰레드가 동시에 메서드를 호출해도 안전합니다.
    """

    def __init__(self, client_signal_handler: ClientSignalHandler, data: MarketData):
        """
        KiwoomMarket의 components들을 생성하고 객체의 attribute를 설정합니다.

        Parameters
        ----------
        client_signal_handler : ClientSignalHandler
            _sig에 등록되어있는 신호를 emit함으로써 키움증권 서버에 요청을 보냅니다.
        data : KiwoomMarketData
            data 객체의 attribute를 접근함으로써 키움증권 서버로부터 온 데이터를 받습니다.
        """
        
        self._sig = client_signal_handler
        self._data = data

    @trace
    def initialize(self) -> None:
        """
        주식시장을 초기화합니다.
        (로그인 -> 계좌번호 로드 -> 초기 잔고 로드)
        
        다른 메서드를 사용하기 전에 오직 한번만 호출되어야 합니다.
        """
        while True:
            self._sig.login_request_signal.emit()
            login_result = self._data.login_result.get()
            if login_result == 0:
                break
        self._sig.account_number_request_signal.emit()
        request_name = KiwoomAPIUtils.create_request_name('GetBalance')
        self._sig.balance_request_signal.emit(request_name)

    @request_api_method
    @trace
    def get_condition(self) -> List[Dict[str, Any]]:
        """
        조건검색식을 로드하고 각각의 이름과 인덱스를 반환합니다.

        Returns
        -------
        List[Dict[str, Any]]
            dict의 list를 반환합니다.
            각 dict는 조건검색식을 의미합니다.
            
            Dict = {
                'name': str,
                'index': int,  
            }
        """
        
        # 동시에 조건검색식을 요청했다면 이에 대한 응답이 서로 뒤바뀔 수 있습니다.
        # 다만 실제 영향은 미미합니다.
        self._sig.condition_request_signal.emit()
        condition_list = self._data.condition_list.get()
        return condition_list

    @request_api_method
    @trace
    def get_matching_stocks(self, condition_name: str, condition_index: int) -> List[str]:
        """
        주어진 조건검색식과 부합하는 주식 코드의 리스트를 반환합니다.
        동일한 condition에 대한 요청은 1분 내 1번으로 제한됩니다.

        Parameters
        ----------
        condition_name : str
            조건검색식의 이름입니다.
        condition_index : int
            조건검색식의 인덱스입니다.

        Returns
        -------
        List[str]
            부합하는 주식 종목의 코드 리스트를 반환합니다.
        """
        
        self._data.condition_name_to_result[condition_name] = queue.Queue(maxsize=1)
        self._sig.condition_search_request_signal.emit(condition_name, condition_index)
        matching_stocks = self._data.condition_name_to_result[condition_name].get()
        del self._data.condition_name_to_result[condition_name]
        return matching_stocks
    
    @request_api_method
    @trace
    def get_deposit(self) -> int:
        """
        계좌의 주문가능금액을 반환합니다.

        Returns
        -------
        int
            주문가능금액을 반환합니다.
        """
        request_name = KiwoomAPIUtils.create_request_name('GetDeposit')
        self._data.request_name_to_tr_data[request_name] = queue.Queue(maxsize=1)
        self._sig.deposit_request_signal.emit(request_name)
        deposit = self._data.request_name_to_tr_data[request_name].get()
        del self._data.request_name_to_tr_data[request_name]
        return deposit
    
    def get_balance(self) -> Dict[str, Dict[str, Any]]:
        """
        보유주식정보를 반환합니다.
        
        주의: 연속조회는 아직 지원되지 않으므로 '시작 할 당시' 보유주식이 많을 경우 
        정보의 일부분만 전송될 수 있습니다.

        Returns
        -------
        Dict[str, Dict[str, Any]]
            보유주식정보를 반환합니다.
            Dict[stock_code] = {
                '종목코드': str,
                '종목명': str,
                '보유수량': int,
                '주문가능수량': int,
                '매입단가': int,
            }
        """
        return self._data.balance
    
    @order_api_method
    @trace
    def request_order(self, order_dict: Dict[str, Any]) -> str:
        """
        주문을 전송합니다.

        Parameters
        ----------
        order_dict : Dict[str, Any]
            order_dict = {
                '구분': '매도' or '매수',
                '주식코드': str,
                '수량': int,
                '가격': int,
                '시장가': bool
            }
            
            시장가 주문을 전송할 경우 가격은 0으로 전달해야 합니다.

        Returns
        -------
        str
            unique한 주문 번호를 반환합니다.
        """
        request_name = KiwoomAPIUtils.create_request_name(f'RequestOrder-{order_dict["주식코드"]}')
        self._data.request_name_to_tr_data[request_name] = queue.Queue(maxsize=1)
        self._sig.order_request_signal.emit(order_dict, request_name)
        order_number = self._data.request_name_to_tr_data[request_name].get()
        del self._data.request_name_to_tr_data[request_name]
        return order_number
 
    @trace
    def get_order_info(self, order_number: str) -> Dict[str, str]:
        """
        주문 번호을 가지고 주문 정보를 얻어옵니다.
        만약 주문이 전부 체결되지 않았다면 체결될 때까지 기다립니다.

        Parameters
        ----------
        order_number : str
            send_order 함수로 얻은 unique한 주문 번호입니다.

        Returns
        -------
        Dict[str, str]
            주문 정보입니다.
        """

        while True:
            try:
                order_info = self._data.order_number_to_info[order_number]
                break
            except KeyError:
                time.sleep(1)
        return order_info 
    
    @trace
    def register_price_info(self, stock_code_list: List[str], is_add: bool = False) -> None:
        """
        주어진 주식 코드에 대한 실시간 가격 정보를 등록합니다.

        Parameters
        ----------
        stock_code_list : List[str]
            실시간 정보를 등록하고 싶은 주식의 코드 리스트입니다.
        is_add : bool, optional
            True일시 화면번호에 존재하는 기존의 등록은 사라집니다.
            False일시 기존에 등록된 종목과 함께 실시간 정보를 받습니다.
            Default로 False입니다.
        """
        self._sig.price_register_request_signal.emit(stock_code_list, is_add)

    @trace
    def register_ask_bid_info(self, stock_code_list: List[str], is_add: bool = False) -> None:
        """
        주어진 주식 코드에 대한 실시간 호가 정보를 등록합니다.

        Parameters
        ----------
        stock_code_list : List[str]
            실시간 정보를 등록하고 싶은 주식의 코드 리스트입니다.
        is_add : bool, optional
            True일시 화면번호에 존재하는 기존의 등록은 사라집니다.
            False일시 기존에 등록된 종목과 함께 실시간 정보를 받습니다.
            Default로 False입니다.
        """
        self._sig.ask_bid_register_request_signal.emit(stock_code_list, is_add)

    @trace
    def get_price_info(self, stock_code: str) -> Dict[str, Any]:
        """
        주어진 주식 코드에 대한 실시간 가격 정보를 가져옵니다.
        주식시장이 과열되면 일정시간동안 거래가 중지되어 정보가 들어오지 않을 수 있습니다.

        Parameters
        ----------
        stock_code : str
            실시간 정보를 가져올 주식 코드입니다.

        Returns
        -------
        Dict[str, Any]
            주어진 주식 코드의 실시간 가격 정보입니다.
            info_dict = {
                '체결시간': str (HHMMSS),
                '현재가': int,
                '시가': int,
                '고가': int,
                '저가': int,
            }
        """
        while True:
            try:
                price_info = self._data.price_info[stock_code]
                break
            except KeyError:
                time.sleep(1)
        
        cur_time = datetime.datetime.now().replace(year=1900, month=1, day=1)
        info_time = price_info['체결시간']
        time_delta = cur_time - info_time
        if time_delta.total_seconds() > 10:
            logger.warning('!!! 실시간 체결 데이터의 시간이 실제 시간과 큰 차이가 있습니다. !!!')
            logger.warning('!!! 주식이 상/하한가이거나 과열될 경우 일어날 수 있습니다. !!!')
            logger.warning(f'!!! {stock_code} - {info_time} vs {cur_time} !!!')
            
        return price_info
    
    @trace
    def get_ask_bid_info(self, stock_code: str) -> Dict[str, Any]:
        """
        주어진 주식 코드에 대한 실시간 호가 정보를 가져옵니다.
        주식시장이 과열되면 일정시간동안 거래가 중지되어 정보가 들어오지 않을 수 있습니다.

        Parameters
        ----------
        stock_code : str
            실시간 정보를 가져올 주식 코드입니다.

        Returns
        -------
        Dict[str, Any]
            주어진 주식 코드의 실시간 호가 정보입니다.
           info_dict = {
                '호가시간': str (HHMMSS),
                '매수호가정보': List[Tuple[int, int]],
                '매도호가정보': List[Tuple[int, int]],
            }
            
            매수호가정보는 (가격, 수량)의 호가정보가 리스트에 1번부터 10번까지 순서대로 들어있습니다.
            매도호가정보도 마찬가지입니다.
        """
        while True:
            try:
                ask_bid_info = self._data.ask_bid_info[stock_code]
                break
            except KeyError:
                time.sleep(1)
        
        cur_time = datetime.datetime.now().replace(year=1900, month=1, day=1)
        info_time = ask_bid_info['호가시간']
        time_delta = cur_time - info_time
        if time_delta.total_seconds() > 10:
            logger.warning('!!! 실시간 호가 데이터의 시간이 실제 시간과 큰 차이가 있습니다. !!!')
            logger.warning('!!! 주식이 상/하한가이거나 과열될 경우 일어날 수 있습니다. !!!')
            logger.warning(f'!!! {stock_code} - {info_time} vs {cur_time} !!!')
        
        return ask_bid_info
            
    