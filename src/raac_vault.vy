# pragma version ^0.4.1
# @license MIT

from ethereum.ercs import IERC20
from modules import vault
from modules import constants
from interfaces import IStrategy

initializes: vault

exports: vault.__interface__


@deploy
def __init__(
    _name: String[25],
    _symbol: String[5],
    _asset: IERC20,
    _decimals_offset_: uint8,
    _name_eip712_: String[50],
    _version_eip712: String[20],
    _strategy: address,
):
    vault.__init__(
        _name, _symbol, _asset, _decimals_offset_, _name_eip712_, _version_eip712, _strategy
    )


@external
def harvest(
    _caller_fee_receiver: address,
    _min_amount_out: uint256,
    _extra_rewards: DynArray[address, constants.MAX_REWARD_TOKENS],
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
    _harvester_calldata: Bytes[4096],
):
    assert vault.access_control.hasRole[vault.HARVESTER_ROLE][msg.sender]
    extcall IStrategy(vault.erc4626.strategy).harvest(
        _caller_fee_receiver,
        _min_amount_out,
        _extra_rewards,
        _reward_hook_calldata,
        _target_hook_calldata,
        _harvester_calldata,
    )
