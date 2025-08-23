from boa.contracts.abi.abi_contract import ABIContractFactory

from tests.utils.abis import BASE_REWARD_POOL_ABI, ERC20_ABI
from tests.utils.constants import (
    CRV_TOKEN,
    CURVE_CVX_ETH_POOL,
    CURVE_TRICRV_POOL,
    CVX_TOKEN,
)

CURVE_POOL_ABI = [
    {
        "name": "get_dy",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "i", "type": "uint256"},
            {"name": "j", "type": "uint256"},
            {"name": "dx", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


def approx(actual, expected, tolerance=1e-3):
    if expected == 0:
        return abs(actual) <= tolerance
    return abs(actual - expected) / abs(expected) <= tolerance


def cvx_to_eth_amount(cvx_amount):
    if cvx_amount == 0:
        return 0
    cvx_eth_pool = ABIContractFactory("CurvePool", CURVE_POOL_ABI).at(
        CURVE_CVX_ETH_POOL
    )
    return cvx_eth_pool.get_dy(1, 0, cvx_amount)


def eth_to_crvusd_amount(eth_amount):
    if eth_amount == 0:
        return 0
    tricrv_pool = ABIContractFactory("CurvePool", CURVE_POOL_ABI).at(
        CURVE_TRICRV_POOL
    )
    return tricrv_pool.get_dy(1, 0, eth_amount)


def crv_to_crvusd_amount(crv_amount):
    if crv_amount == 0:
        return 0
    tricrv_pool = ABIContractFactory("CurvePool", CURVE_POOL_ABI).at(
        CURVE_TRICRV_POOL
    )
    eth_amount = tricrv_pool.get_dy(2, 1, crv_amount)
    return tricrv_pool.get_dy(1, 0, eth_amount)


def cvx_to_crvusd_amount(cvx_amount):
    if cvx_amount == 0:
        return 0
    eth_amount = cvx_to_eth_amount(cvx_amount)
    return eth_to_crvusd_amount(eth_amount)


def calc_gross_harvest_amount(strategy_addr, rewards_contract_addr):
    rewards_contract = ABIContractFactory(
        "BaseRewardPool", BASE_REWARD_POOL_ABI
    ).at(rewards_contract_addr)
    crv_token = ABIContractFactory("ERC20", ERC20_ABI).at(CRV_TOKEN)
    cvx_token = ABIContractFactory("ERC20", ERC20_ABI).at(CVX_TOKEN)

    pending_crv = rewards_contract.earned(strategy_addr)
    current_crv = crv_token.balanceOf(strategy_addr)
    total_crv = pending_crv + current_crv

    current_cvx = cvx_token.balanceOf(strategy_addr)
    total_cvx = pending_crv + current_cvx

    crv_value_in_crvusd = crv_to_crvusd_amount(total_crv)
    cvx_value_in_crvusd = cvx_to_crvusd_amount(total_cvx)

    return crv_value_in_crvusd + cvx_value_in_crvusd


def calc_expected_fees(gross_harvest, platform_fee_bps, caller_fee_bps):
    platform_fees = gross_harvest * platform_fee_bps // 10000
    caller_fees = gross_harvest * caller_fee_bps // 10000
    net_harvest = gross_harvest - platform_fees - caller_fees
    return platform_fees, caller_fees, net_harvest
