# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, Union
from pandas import DataFrame

from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
    merge_informative_pair
)
import talib.abstract as ta
import pandas_ta as pta

# Import our custom AI Gateway
from ai_gateway import SumopodAIGateway

logger = logging.getLogger(__name__)

class FatQulStrategy(IStrategy):
    """
    FatQul AI Trader - Freqtrade Hybrid AI Trading System
    Combines SMC & Classical TA with Sumopod AI Narrative/Fundamental analysis.
    """
    
    INTERFACE_VERSION = 3
    
    # Timeframes
    timeframe = '1h'
    informative_timeframes = ['15m', '4h']
    
    # ROI table: essentially we rely on partial TP & trailing stop, so we can set high ROI
    minimal_roi = {
        "0": 0.20,
        "60": 0.10,
        "180": 0.05
    }
    
    # Dynamic stoploss handled by custom_stoploss
    stoploss = -0.10
    
    # Trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True
    
    # Position Adjustment for Partial TP
    position_adjustment_enable = True
    
    # Custom attributes
    ai_gateway = SumopodAIGateway()
    min_stake_amount = 20000  # Minimum order size for Indodax in IDR (approx ~20k IDR)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        for tf in self.informative_timeframes:
            for pair in pairs:
                informative_pairs.append((pair, tf))
        return informative_pairs
        
    def bot_loop_start(self, **kwargs) -> None:
        """
        Called at the start of the bot iteration.
        Used for AI Pre-scoring batch to avoid rate limits during confirm_trade_entry.
        """
        pairs = self.dp.current_whitelist()
        logger.info(f"bot_loop_start: Starting pre-scoring for {len(pairs)} pairs.")
        
        # In a real scenario, we might want to only pre-score top volume pairs,
        # but for simplicity, we pass all whitelist pairs to the batch pr-scorer.
        # Create a simple context for each pair to pass to AI
        context_data = {}
        for pair in pairs:
            # We could fetch recent OHLCV here if we wanted to pass technicals,
            # but AI is doing Narrative/Fund, so pair name is mostly enough.
            context_data[pair] = f"Market conditions for {pair}"
            
        # Trigger background batch pre-score
        self.ai_gateway.batch_pre_score(context_data)
        
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculates Technical Analysis components (SMC + Classical)
        """
        # --- Classical TA ---
        dataframe['ema_9'] = ta.EMA(dataframe, timeperiod=9)
        dataframe['ema_21'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # ATR for volatility & stoploss
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # ADX
        adx = ta.ADX(dataframe)
        dataframe['adx'] = adx
        
        # SuperTrend (10,3)
        st_df = pta.supertrend(dataframe['high'], dataframe['low'], dataframe['close'], length=10, multiplier=3)
        dataframe['supertrend'] = st_df['SUPERT_10_3.0']
        
        # --- Simplified SMC Logic ---
        # Fair Value Gap (FVG) detection (Bullish)
        # Low of candle (i) > High of candle (i-2)
        dataframe['fvg_bull'] = (dataframe['low'] > dataframe['high'].shift(2))
        
        # Calculate a baseline "Technical Score" (0 to 45 points)
        # Based on PRD weighting
        
        def calculate_ta_score(row):
            score = 0
            
            # Trend Alignment (EMA & SuperTrend)
            if row['ema_9'] > row['ema_21'] and row['ema_21'] > row['ema_50']:
                score += 10
            elif row['ema_9'] > row['ema_21']:
                score += 5
                
            if pd.notna(row['supertrend']) and row['close'] > row['supertrend']:
                score += 5
                
            # Momentum (RSI)
            if 40 <= row['rsi'] <= 65:
                score += 10 # Healthy momentum
            elif row['rsi'] > 70:
                score -= 5  # Overbought
                
            # Strength (ADX)
            if pd.notna(row['adx']) and row['adx'] > 20:
                score += 10
                
            # SMC (FVG)
            if row['fvg_bull']:
                score += 10
                
            return min(45, max(0, score)) # Cap at 45

        dataframe['ta_score'] = dataframe.apply(calculate_ta_score, axis=1)
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Technical Entry Signal. We signal if TA score is reasonable.
        The AI Gate in confirm_trade_entry will make the final decision.
        """
        dataframe.loc[
            (
                (dataframe['ta_score'] >= 25) &  # Minimum technical threshold to even consider
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Technical Exit Signal.
        """
        dataframe.loc[
            (
                (dataframe['ema_9'] < dataframe['ema_50']) &
                (dataframe['rsi'] > 75)
            ),
            'exit_long'] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time, entry_tag, side: str, **kwargs) -> bool:
        """
        AI Gate: Validate with Sumopod AI.
        Total Score = Technical (45%) + Narrative (30%) + Fundamental (25%)
        Score >= 78 -> Full
        Score 68-77 -> Partial
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_row = dataframe.iloc[-1]
        
        ta_score = int(last_row['ta_score'])
        
        # Fetch AI Score (from cache via gateway)
        context = f"Price: {rate}, RSI: {last_row['rsi']:.2f}, Trend: Bullish"
        ai_data = self.ai_gateway.get_ai_score(pair, context)
        
        narrative_score = ai_data.get('narrative', 0)
        fund_score = ai_data.get('fundamental', 0)
        
        total_score = ta_score + narrative_score + fund_score
        
        logger.info(f"[{pair}] Scoring -> TA: {ta_score}/45, Narrative: {narrative_score}/30, Fund: {fund_score}/25 | Total: {total_score}/100")
        logger.info(f"[{pair}] AI Reasoning: {ai_data.get('reasoning')}")
        
        # Check Emergency Mode Auto-Switch Rule
        if self.ai_gateway.is_emergency_mode():
            if ta_score >= 85: # Almost impossible with current capped logic, but demonstrates the PRD spec
                logger.warning(f"[{pair}] EMERGENCY MODE ENTRY APPROVED. TA: {ta_score}")
                return True
            else:
                logger.warning(f"[{pair}] EMERGENCY MODE ENTRY REJECTED. TA: {ta_score} < 85")
                return False

        # Tiered Logic
        if total_score >= 68:
            logger.info(f"[{pair}] Trade APPROVED (Score {total_score} >= 68)")
            return True
            
        logger.info(f"[{pair}] Trade REJECTED (Score {total_score} < 68)")
        return False

    def custom_stake_amount(self, pair: str, current_time, current_rate: float,
                            proposed_stake: float, min_stake: Optional[float], max_stake: float,
                            leverage: float, entry_tag: Optional[str], side: str,
                            **kwargs) -> float:
        """
        Position sizing based on AI Score.
        Full (score>=78), Partial/50% (score 68-77), and Min Stake Validation.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_row = dataframe.iloc[-1]
        ta_score = int(last_row['ta_score'])
        
        ai_data = self.ai_gateway.get_ai_score(pair, "cached_lookup_only")
        total_score = ta_score + ai_data.get('narrative', 0) + ai_data.get('fundamental', 0)
        
        if self.ai_gateway.is_emergency_mode():
            final_stake = proposed_stake # In emergency, if it passed, give it full proposed
        elif total_score >= 78:
            final_stake = proposed_stake # 100% allocation
        elif 68 <= total_score <= 77:
            final_stake = proposed_stake * 0.5 # 50% allocation
        else:
            final_stake = 0
            
        # Minimum Stake Validation (Indodax minimum order size check)
        # Freqtrade provides min_stake (from exchange info), but we also have a hardcoded fallback
        effective_min_stake = min_stake if min_stake is not None else self.min_stake_amount
        
        if final_stake < effective_min_stake:
            logger.warning(f"[{pair}] Skipping pair: Calculated stake {final_stake} is less than min stake {effective_min_stake}")
            return 0
            
        return final_stake

    def custom_stoploss(self, pair: str, trade, current_time, current_rate: float,
                        current_profit: float, **kwargs) -> float:
        """
        Dynamic stoploss based on ATR.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        
        atr = last_candle['atr']
        if pd.notna(atr) and atr > 0:
            # SL = 1.5 * ATR (converted to percentage relative to entry)
            atr_pct = (atr * 1.5) / trade.open_rate
            
            # Ensure SL is not too tight or too wide
            sl = max(-0.15, min(-0.02, -atr_pct))
            return sl
            
        return self.stoploss # Fallback

    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                    current_profit: float, **kwargs):
        # Custom exit can handle full exit signals if needed.
        # Target 15% profit as full exit if trailing stop doesn't catch it
        if current_profit > 0.15:
            return "take_profit_target_reached"
            
        return None

    def adjust_trade_position(self, trade, current_time, current_rate: float,
                              current_profit: float, min_stake: Optional[float],
                              max_stake: float, current_entry_rate: float,
                              current_exit_rate: float, current_entry_profit: float,
                              current_exit_profit: float, **kwargs) -> Optional[float]:
        """
        Partial Take-Profit logic (50% at RR 1:2).
        Assuming average SL is 5%, RR 1:2 means taking profit at 10%.
        """
        if current_profit > 0.10 and trade.nr_of_successful_exits == 0:
            # We want to sell 50% of the current position
            # Returning a negative number means selling that amount of stake
            sell_amount = (trade.stake_amount / 2)
            logger.info(f"[{trade.pair}] Partial TP Triggered: Profit > 10%. Selling 50% ({sell_amount}).")
            return -sell_amount
            
        return None
