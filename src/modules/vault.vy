# pragma version 0.4.3
# @license MIT

from ethereum.ercs import IERC20
from snekmate.auth import access_control
from src.modules import erc4626
from src.interfaces import IStrategy
from src.interfaces import IVaultFactory
from src.interfaces import IHarvester

initializes: access_control
initializes: erc4626
exports: (
    erc4626.DOMAIN_SEPARATOR,
    erc4626.allowance,
    erc4626.approve,
    erc4626.asset,
    erc4626.balanceOf,
    erc4626.convertToAssets,
    erc4626.convertToShares,
    erc4626.decimals,
    erc4626.deposit,
    erc4626.eip712Domain,
    erc4626.maxDeposit,
    erc4626.maxMint,
    erc4626.maxRedeem,
    erc4626.maxWithdraw,
    erc4626.mint,
    erc4626.name,
    erc4626.nonces,
    erc4626.permit,
    erc4626.previewDeposit,
    erc4626.previewMint,
    erc4626.previewRedeem,
    erc4626.previewWithdraw,
    erc4626.redeem,
    erc4626.strategy,
    erc4626.symbol,
    erc4626.totalAssets,
    erc4626.totalSupply,
    erc4626.transfer,
    erc4626.transferFrom,
    erc4626.withdraw,
)

exports: (
    access_control.DEFAULT_ADMIN_ROLE,
    access_control.getRoleAdmin,
    access_control.grantRole,
    access_control.hasRole,
    access_control.renounceRole,
    access_control.revokeRole,
    access_control.set_role_admin,
    access_control.supportsInterface,
)

last_harvest: public(uint256)

# Access control roles
STRATEGY_MANAGER_ROLE: public(constant(bytes32)) = keccak256("STRATEGY_MANAGER_ROLE")

# Can be made permissionless by setting to a permissionless proxy contract
HARVESTER_ROLE: public(constant(bytes32)) = keccak256("HARVESTER_ROLE")


@deploy
def __init__(
    _name: String[25],
    _symbol: String[5],
    _asset: IERC20,
    _decimals_offset: uint8,
    _name_eip712: String[50],
    _version_eip712: String[20],
    _strategy: address,
):
    """
    @dev Contract deployer will have the DEFAULT_ADMIN_ROLE on the vault
    """
    assert _strategy != empty(address), "No strategy"
    access_control.__init__()
    erc4626.__init__(
        _name,
        _symbol,
        _asset,
        _decimals_offset,
        _name_eip712,
        _version_eip712,
        _strategy,
    )


@external
def set_platform_fee(_new_platform_fee: uint256):
    assert access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
    extcall IStrategy(erc4626.strategy).set_platform_fee(_new_platform_fee)


@external
def set_caller_fee(_new_caller_fee: uint256):
    assert access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
    extcall IStrategy(erc4626.strategy).set_caller_fee(_new_caller_fee)


@external
def update_harvester(_new_harvester: address):
    assert access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
    harvester: address = staticcall IStrategy(erc4626.strategy).harvester()
    factory: address = staticcall IHarvester(harvester).factory()
    extcall IStrategy(erc4626.strategy).update_harvester(_new_harvester)
    extcall IVaultFactory(factory).update_harvester(_new_harvester)


@external
def set_extra_reward_hook(_new_hook: address):
    assert (
        access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
        or access_control.hasRole[access_control.DEFAULT_ADMIN_ROLE][msg.sender]
    )
    extcall IStrategy(erc4626.strategy).set_extra_reward_hook(_new_hook)


@external
def set_target_hook(_new_hook: address):
    assert (
        access_control.hasRole[STRATEGY_MANAGER_ROLE][msg.sender]
        or access_control.hasRole[access_control.DEFAULT_ADMIN_ROLE][msg.sender]
    )
    extcall IStrategy(erc4626.strategy).set_target_hook(_new_hook)
