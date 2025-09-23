# pragma version 0.4.3
# pragma nonreentrancy on
# @license MIT

"""
@title RAAC Vault
@custom:contract-name raac_vault
@author RAAC
@notice ERC4626 compliant vault for autocompounding Convex Finance yield
@dev This contract implements the ERC4626 standard for tokenized vaults and manages
     user deposits/withdrawals while delegating strategy execution to a separate
     strategy contract. It provides role-based access control for harvesting and
     strategy management operations. The vault automatically compounds rewards from
     the underlying Convex Finance positions through coordinated harvest operations.

"""

from ethereum.ercs import IERC20
from src.modules import vault

initializes: vault

exports: (
    vault.DEFAULT_ADMIN_ROLE,
    vault.DOMAIN_SEPARATOR,
    vault.HARVESTER_ROLE,
    vault.STRATEGY_MANAGER_ROLE,
    vault.allowance,
    vault.approve,
    vault.asset,
    vault.balanceOf,
    vault.convertToAssets,
    vault.convertToShares,
    vault.decimals,
    vault.deposit,
    vault.eip712Domain,
    vault.full_profit_unlock_date,
    vault.getRoleAdmin,
    vault.grantRole,
    vault.harvest,
    vault.hasRole,
    vault.last_harvest,
    vault.locked_shares,
    vault.maxDeposit,
    vault.maxMint,
    vault.maxRedeem,
    vault.maxWithdraw,
    vault.mint,
    vault.name,
    vault.nonces,
    vault.permit,
    vault.previewDeposit,
    vault.previewMint,
    vault.previewRedeem,
    vault.previewWithdraw,
    vault.profit_max_unlock_time,
    vault.profit_unlocking_rate,
    vault.raw_total_supply,
    vault.raw_vault_balance,
    vault.redeem,
    vault.renounceRole,
    vault.revokeRole,
    vault.set_caller_fee,
    vault.set_extra_reward_hook,
    vault.set_platform_fee,
    vault.set_profit_max_unlock_time,
    vault.set_role_admin,
    vault.set_target_hook,
    vault.strategy,
    vault.supportsInterface,
    vault.symbol,
    vault.totalAssets,
    vault.totalSupply,
    vault.transfer,
    vault.transferFrom,
    vault.unlock_scale,
    vault.unlocked_shares,
    vault.migrate_booster,
    vault.admin_unwind_rewards,
    vault.update_harvester,
    vault.withdraw,
    vault.MIN_SHARES,
)


@deploy
def __init__(
    _name: String[25],
    _symbol: String[5],
    _asset: IERC20,
    _decimals_offset_: uint8,
    _name_eip712_: String[50],
    _version_eip712: String[20],
    _strategy: address,
    _profit_max_unlock_time: uint256,
):
    vault.__init__(
        _name,
        _symbol,
        _asset,
        _decimals_offset_,
        _name_eip712_,
        _version_eip712,
        _strategy,
        _profit_max_unlock_time,
    )
