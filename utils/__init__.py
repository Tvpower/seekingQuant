"""
SeekingQuant Trading Utilities

This package contains trading utilities with a common module for shared functions.
"""

from .trading_common import (
    # Symbol normalization
    normalize_symbol,
    ibkr_symbol,
    
    # IBKR connection management
    connect_to_ibkr,
    disconnect_from_ibkr,
    
    # Account management
    get_available_accounts,
    select_account,
    
    # Report generation
    generate_trade_report,
    
    # Command line utilities
    parse_trading_args,
    
    # Display utilities
    print_header,
    print_section,
    confirm_action,
)

__all__ = [
    # Symbol normalization
    'normalize_symbol',
    'ibkr_symbol',
    
    # IBKR connection management
    'connect_to_ibkr',
    'disconnect_from_ibkr',
    
    # Account management
    'get_available_accounts',
    'select_account',
    
    # Report generation
    'generate_trade_report',
    
    # Command line utilities
    'parse_trading_args',
    
    # Display utilities
    'print_header',
    'print_section',
    'confirm_action',
]

