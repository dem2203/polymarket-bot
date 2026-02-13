"""
Health Monitor - Bot Self-Monitoring & Alerting System

Prevents silent failures by:
1. Detecting impossible/critical states (negative cash, monitoring failures)
2. Sending immediate Telegram alerts
3. Tracking activity metrics (last trade, monitoring times)
4. Auto-recovery mechanisms
5. 6-hour health dashboard reports
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HealthMetrics:
    """Activity and health tracking metrics."""
    last_trade_time: Optional[datetime] = None
    last_monitoring_time: Optional[datetime] = None
    last_positive_cash_time: Optional[datetime] = None
    trades_today: int = 0
    monitoring_failures: int = 0
    critical_alerts_sent: int = 0
    warning_alerts_sent: int = 0
    
    # Alert rate limiting
    last_alert_times: Dict[str, datetime] = field(default_factory=dict)


class HealthMonitor:
    """
    Self-monitoring system for bot health.
    
    Detects critical issues and sends immediate alerts:
    - Negative cash (impossible state)
    - Position monitoring failures
    - Idle trading (6+ hours with available cash)
    - Balance sanity check failures
    """
    
    def __init__(self, telegram_notifier):
        self.telegram = telegram_notifier
        self.metrics = HealthMetrics()
        
        # Alert rate limiting (max 1 per hour per type)
        self.alert_cooldown = timedelta(hours=1)
        
        # Thresholds (configurable)
        self.idle_threshold_hours = 6
        self.monitoring_success_threshold = 0.5  # 50% of positions need price data
        self.balance_min = 1.0  # Minimum expected balance
        self.balance_max = 1000.0  # Maximum expected balance
        
    def record_trade(self):
        """Record a trade execution."""
        self.metrics.last_trade_time = datetime.now(timezone.utc)
        self.metrics.trades_today += 1
        logger.debug(f"✅ Trade recorded. Today: {self.metrics.trades_today}")
        
    def record_monitoring(self):
        """Record successful position monitoring."""
        self.metrics.last_monitoring_time = datetime.now(timezone.utc)
        logger.debug("✅ Monitoring recorded")
        
    def record_monitoring_failure(self):
        """Record position monitoring failure."""
        self.metrics.monitoring_failures += 1
        logger.warning(f"⚠️ Monitoring failure recorded. Total: {self.metrics.monitoring_failures}")
        
    def record_positive_cash(self):
        """Record that cash is positive."""
        self.metrics.last_positive_cash_time = datetime.now(timezone.utc)
        
    # ==================== CRITICAL ALERTS ====================
    
    async def check_negative_cash(self, available_cash: float, balance: float, total_exposure: float) -> bool:
        """
        CRITICAL: Check for negative available cash (IMPOSSIBLE state).
        
        Returns:
            True if cash is negative (emergency stop required)
        """
        if available_cash < 0:
            await self._send_critical_alert(
                "NEGATIVE_CASH",
                "🚨 NEGATIVE CASH DETECTED",
                f"Available: ${available_cash:.2f}\n"
                f"Balance: ${balance:.2f}\n"
                f"Total Exposure: ${total_exposure:.2f}\n\n"
                f"⛔ **EMERGENCY STOP - ALL TRADING HALTED**\n"
                f"This is an impossible state indicating:\n"
                f"• Data corruption\n"
                f"• Stale position tracking\n"
                f"• API error\n\n"
                f"Action: Bot stopped, manual intervention required."
            )
            return True
        
        # Record positive cash
        self.record_positive_cash()
        return False
        
    async def check_monitoring_failure(
        self, 
        open_positions_count: int, 
        market_prices_count: int
    ) -> bool:
        """
        Check if position monitoring failed to fetch prices.
        
        Returns:
            True if monitoring critically degraded
        """
        if open_positions_count == 0:
            return False
            
        success_rate = market_prices_count / open_positions_count if open_positions_count > 0 else 1.0
        
        if success_rate < self.monitoring_success_threshold:
            self.record_monitoring_failure()
            
            await self._send_critical_alert(
                "MONITORING_FAILURE",
                "🚨 POSITION MONITORING FAILURE",
                f"Open Positions: {open_positions_count}\n"
                f"Price Data Fetched: {market_prices_count}\n"
                f"Success Rate: {success_rate:.1%}\n\n"
                f"⚠️ **CRITICAL RISK**\n"
                f"• Stop Loss NOT executing\n"
                f"• Take Profit NOT executing\n"
                f"• Smart Expiry Exit NOT working\n\n"
                f"Action: Monitoring continuing with degraded functionality."
            )
            return True
        
        # Success
        self.record_monitoring()
        return False
        
    async def check_idle_trading(self, available_cash: float):
        """
        Check if bot has been idle for 6+ hours with available cash.
        """
        if not self.metrics.last_trade_time:
            return  # No trades yet (bot just started)
            
        now = datetime.now(timezone.utc)
        hours_since_trade = (now - self.metrics.last_trade_time).total_seconds() / 3600
        
        if hours_since_trade > self.idle_threshold_hours and available_cash > 5.0:
            await self._send_warning_alert(
                "IDLE_TRADING",
                "⚠️ BOT IDLE FOR 6+ HOURS",
                f"Last Trade: {hours_since_trade:.1f}h ago\n"
                f"Available Cash: ${available_cash:.2f}\n\n"
                f"Possible Issues:\n"
                f"• Market Scanner: No opportunities found\n"
                f"• AI Analysis: All signals rejected\n"
                f"• Risk Manager: Blocking trades\n\n"
                f"Action: Investigate bot logs for root cause."
            )
            
    async def check_balance_sanity(self, balance: float):
        """
        Sanity check: Balance should be in expected range.
        """
        if balance < self.balance_min or balance > self.balance_max:
            await self._send_critical_alert(
                "BALANCE_SANITY",
                "🚨 BALANCE SANITY CHECK FAILED",
                f"Balance: ${balance:.2f}\n"
                f"Expected Range: ${self.balance_min:.2f} - ${self.balance_max:.2f}\n\n"
                f"Possible Issues:\n"
                f"• API returning incorrect data\n"
                f"• Wallet compromised (if too low)\n"
                f"• Unexpected deposit (if too high)\n\n"
                f"Action: Verify balance on Polymarket web interface."
            )
            
    # ==================== DEFENSIVE VALIDATION ====================
    
    def validate_monitoring_executed(
        self, 
        open_positions_count: int, 
        market_prices_count: int
    ) -> bool:
        """
        Validate that monitoring actually ran and fetched data.
        
        Returns:
            True if monitoring executed successfully
        """
        if open_positions_count == 0:
            return True  # No positions to monitor
            
        success_rate = market_prices_count / open_positions_count if open_positions_count > 0 else 0.0
        
        if success_rate >= self.monitoring_success_threshold:
            return True
        
        logger.error(
            f"🔴 Monitoring validation failed: {market_prices_count}/{open_positions_count} "
            f"positions have price data ({success_rate:.1%})"
        )
        return False
        
    # ==================== AUTO-RECOVERY ====================
    
    async def trigger_emergency_stop(self, reason: str):
        """
        Emergency stop: Halt all trading and alert user.
        """
        logger.critical(f"🛑 EMERGENCY STOP: {reason}")
        await self.telegram.send_critical_alert(
            "🛑 EMERGENCY STOP",
            f"Reason: {reason}\n\n"
            f"Bot has been halted.\n"
            f"Manual intervention required to restart."
        )
        
    # ==================== HEALTH DASHBOARD ====================
    
    def calculate_health_score(self, available_cash: float) -> float:
        """
        Calculate health score (0-100).
        
        Deductions:
        - 20pts: No trades in 6+ hours (with cash)
        - 30pts: No monitoring in 1+ hour
        - 10pts per monitoring failure
        - 20pts per critical alert
        - 15pts: Low cash (< $2)
        """
        score = 100.0
        now = datetime.now(timezone.utc)
        
        # Last trade check
        if self.metrics.last_trade_time:
            hours_since_trade = (now - self.metrics.last_trade_time).total_seconds() / 3600
            if hours_since_trade > 6 and available_cash > 5:
                score -= 20
                
        # Last monitoring check
        if self.metrics.last_monitoring_time:
            hours_since_monitoring = (now - self.metrics.last_monitoring_time).total_seconds() / 3600
            if hours_since_monitoring > 1:
                score -= 30
                
        # Monitoring failures
        score -= 10 * min(self.metrics.monitoring_failures, 5)
        
        # Critical alerts
        score -= 20 * min(self.metrics.critical_alerts_sent, 3)
        
        # Low cash
        if available_cash < 2:
            score -= 15
            
        return max(0, min(100, score))
        
    def get_health_status(self, score: float) -> tuple[str, str]:
        """
        Get health status emoji and text.
        
        Returns:
            (emoji, status_text)
        """
        if score >= 90:
            return "🟢", "EXCELLENT"
        elif score >= 60:
            return "🟡", "DEGRADED"
        else:
            return "🔴", "CRITICAL"
            
    async def send_health_dashboard(
        self, 
        balance: float,
        positions_tracker,
        perf_tracker
    ):
        """
        Send 6-hour health dashboard to Telegram.
        """
        now = datetime.now(timezone.utc)
        
        # Calculate metrics
        available_cash = balance
        health_score = self.calculate_health_score(available_cash)
        status_emoji, status_text = self.get_health_status(health_score)
        
        # Activity metrics
        last_trade_str = "Never"
        if self.metrics.last_trade_time:
            delta = now - self.metrics.last_trade_time
            hours = delta.total_seconds() / 3600
            if hours < 1:
                last_trade_str = f"{int(delta.total_seconds() / 60)} minutes ago"
            else:
                last_trade_str = f"{hours:.1f} hours ago"
                
        last_monitoring_str = "Never"
        if self.metrics.last_monitoring_time:
            delta = now - self.metrics.last_monitoring_time
            minutes = delta.total_seconds() / 60
            last_monitoring_str = f"{int(minutes)} minutes ago"
            
        # Performance metrics
        stats = perf_tracker.get_stats() if perf_tracker else {}
        portfolio_summary = positions_tracker.get_portfolio_summary(balance)
        
        # Build dashboard
        dashboard = f"""📊 **HEALTH DASHBOARD** {status_emoji}

⏰ **Activity**
├─ Last Trade: {last_trade_str}
├─ Last Monitoring: {last_monitoring_str}
└─ Trades Today: {self.metrics.trades_today}

💰 **Economics**
├─ Balance: ${balance:.2f}
├─ Open Positions: {len(positions_tracker.open_positions)}
└─ Portfolio Value: ${portfolio_summary.get('total_value', balance):.2f}

📈 **Performance**
├─ Total Trades: {stats.get('total_trades', 0)}
├─ Win Rate: {stats.get('win_rate', 0):.1%}
└─ Total PnL: ${stats.get('total_pnl', 0):.2f}

🏥 **Health Score: {health_score:.0f}/100** {status_emoji}
└─ Status: {status_text}

📊 **Issues**
├─ Monitoring Failures: {self.metrics.monitoring_failures}
├─ Critical Alerts: {self.metrics.critical_alerts_sent}
└─ Warnings: {self.metrics.warning_alerts_sent}
"""

        await self.telegram.send_message(dashboard)
        
    def reset_daily_metrics(self):
        """Reset daily counters (call at midnight UTC)."""
        self.metrics.trades_today = 0
        logger.info("📊 Daily metrics reset")
        
    # ==================== INTERNAL HELPERS ====================
    
    async def _send_critical_alert(self, alert_type: str, title: str, message: str):
        """Send critical alert with rate limiting."""
        if not self._should_send_alert(alert_type):
            logger.warning(f"🔇 Alert rate-limited: {alert_type}")
            return
            
        self.metrics.critical_alerts_sent += 1
        self.metrics.last_alert_times[alert_type] = datetime.now(timezone.utc)
        
        await self.telegram.send_critical_alert(title, message)
        logger.critical(f"🚨 CRITICAL ALERT SENT: {alert_type}")
        
    async def _send_warning_alert(self, alert_type: str, title: str, message: str):
        """Send warning alert with rate limiting."""
        if not self._should_send_alert(alert_type):
            logger.debug(f"🔇 Alert rate-limited: {alert_type}")
            return
            
        self.metrics.warning_alerts_sent += 1
        self.metrics.last_alert_times[alert_type] = datetime.now(timezone.utc)
        
        await self.telegram.send_warning_alert(title, message)
        logger.warning(f"⚠️ WARNING ALERT SENT: {alert_type}")
        
    def _should_send_alert(self, alert_type: str) -> bool:
        """Check if alert should be sent (rate limiting)."""
        if alert_type not in self.metrics.last_alert_times:
            return True
            
        last_sent = self.metrics.last_alert_times[alert_type]
        elapsed = datetime.now(timezone.utc) - last_sent
        
        return elapsed > self.alert_cooldown
