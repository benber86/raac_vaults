# pragma version 0.4.3
# pragma nonreentrancy on

"""
@title CoW Protocol Conditional Order Handler
@custom:contract-name cow_conditional_order
@license MIT
@author RAAC
@notice A contract for creating and managing CoW Protocol conditional orders
@dev CowSwap swaps are asynchronous meaning that harvests can't be done atomically
     Instead, the harvester will use rewards from the previous harvest to forward
     to the strategy for autocompounding.
     The workflow is as follows:
     - A harvest call will specify the tokens to sell and the minimum amount of crvUSD expected for each
     - The contract will create a CowSwap order if needed or update its validity if the last order has expired
     - The contract will sweep the crvUSD rewards obtained from the *previous* harvest to pay out the caller fee
       and use for autocompounding.
     - The contract will call the target hook to swap the crvUSD to the target LP token and forward it to the strategy
     - Later, the cowswap order will be picked up and filled by searchers who will return crvUSD to the contract
       which will be used for the *next* harvest
     Each order is valid for a certain period of time. The period should not be too long because orders will
     remain outstanding even after being filled. If rewards reach the previous sell_amount quantity they can be
     sold again - however the price specified in buy_amount may be too low and result in subpar execution
"""

from ethereum.ercs import IERC20
from src.interfaces import IStrategy
from src.interfaces import IVault
from src.modules import constants
from src.modules.swappers import swapper

initializes: swapper

exports: constants.MAX_TOKENS

exports: (
    swapper.extra_reward_hook,
    swapper.factory,
    swapper.set_extra_reward_hook,
    swapper.set_strategy,
    swapper.set_target_hook,
    swapper.strategy,
    swapper.target_hook,
    swapper.transfer_to_reward_hook,
    swapper.transfer_to_target_hook,
    swapper.treasury,
    swapper.forward_tokens,
    swapper.__default__,
)


interface IComposableCoW:
    def create(params: ConditionalOrderParams, dispatch: bool): nonpayable
    def remove(singleOrderHash: bytes32): nonpayable
    def hash(params: ConditionalOrderParams) -> bytes32: pure
    def domainSeparator() -> bytes32: view
    def isValidSafeSignature(
        safe: address,
        sender: address,
        _hash: bytes32,
        _domainSeparator: bytes32,
        typeHash: bytes32,
        encodeData: Bytes[15 * 32],
        payload: Bytes[(32 + 3 + 1 + 8) * 32],
    ) -> bytes4: view


# Used to uniquely identify a conditional order for an owner.
struct ConditionalOrderParams:
    # The contract implementing the conditional order logic = the present contract
    handler: address
    # Allows for multiple conditional orders of the same type and data
    salt: bytes32
    # Data available to ALL discrete orders created by the conditional order
    staticInput: Bytes[20]


struct Payload:
    proof: DynArray[bytes32, 32]
    params: ConditionalOrderParams
    offchainInput: Bytes[20]


# The complete data for a Gnosis Protocol order. This struct contains
# all order parameters that are signed for submitting to GP.
struct GPv2OrderData:
    # ERC-20 token sell
    sellToken: address
    # ERC-20 token to buy
    buyToken: address
    # The address that will receive the proceedings of the trade. If this field is
    # address(0) (i.e. the zero address 0x00...0), then the user who signed the trade
    # is going to receive the funds.
    receiver: address
    # Amount of sellToken that is sold in wei.
    sellAmount: uint256
    # Amount of buyToken that is bought in wei
    buyAmount: uint256
    # UNIX timestamp (in seconds) until which the order is valid
    validTo: uint32
    # Extra information about the order. Not enforced by the smart contract outside
    # of signature verification (may be used for referrals etc).
    appData: bytes32
    # Amount of fees paid in sellToken wei
    feeAmount: uint256
    # "sell" or "buy" (keccak hashed)
    kind: bytes32
    # partially fillable (true) or fill-or-kill (false)
    partiallyFillable: bool
    # From where the sellToken balance is withdrawn
    sellTokenBalance: bytes32
    # Where the buyToken is deposited
    buyTokenBalance: bytes32


struct SwapParams:
    sellToken: address
    buyToken: address
    sellAmount: uint256
    minBuyAmount: uint256
    validTo: uint32
    partiallyFillable: bool


struct TokenOrderInfo:
    last_order_time: uint256
    buy_amount: uint256
    sell_amount: uint256


COMPOSABLE_COW: public(constant(address)) = 0xfdaFc9d1902f4e0b84f65F49f244b32b31013b74
VAULT_RELAYER: public(constant(address)) = 0xC92E8bdf79f0507f65a392b0ab4667716BFE0110
ORDER_KIND_SELL: constant(bytes32) = keccak256("sell")
BALANCE_ERC20: constant(bytes32) = keccak256("erc20")
# https://explorer.cow.fi/appdata?tab=encode
APP_DATA: constant(bytes32) = empty(bytes32)

SUPPORTED_INTERFACES: constant(bytes4[3]) = [
    0x1626ba7e,  # isValidSignature(bytes32,bytes) / ERC1271_MAGIC_VALUE
    0x01ffc9a7,  # supportsInterface(bytes4)
    0xb8296fc4,  # getTradeableOrder(address,address,bytes32,bytes,bytes)
]
SIGNATURE_VERIFIER_MUXER_INTERFACE: constant(bytes4) = 0x62af8dc2
DAY: constant(uint256) = 60 * 60 * 24
delay: public(uint256)

token_order_info: public(HashMap[address, TokenOrderInfo])
token_orders: HashMap[address, bool]


event DelayUpdated:
    delay: uint256


event ConditionalOrderCancelled:
    token: indexed(address)
    hash: bytes32


@deploy
def __init__(_factory: address):
    swapper.__init__(_factory)
    self.delay = DAY


@external
def set_delay(delay: uint256):
    vault: IVault = IVault(staticcall IStrategy(swapper.strategy).vault())
    assert staticcall vault.hasRole(staticcall vault.HARVESTER_ROLE(), msg.sender), "Manager only"
    assert (delay < DAY * 7), "Delay too long"
    self.delay = delay
    log DelayUpdated(delay=delay)


@external
def set_approvals():
    """
    @notice Set token approvals for COW Protocol vault relayer
    @dev Approves CRV and CVX tokens for swapping via COW Protocol
    """
    # CRV token approval
    assert extcall IERC20(constants.CRV_TOKEN).approve(VAULT_RELAYER, 0, default_return_value=True)
    assert extcall IERC20(constants.CRV_TOKEN).approve(
        VAULT_RELAYER, max_value(uint256), default_return_value=True
    )
    # CVX token approval
    assert extcall IERC20(constants.CVX_TOKEN).approve(VAULT_RELAYER, 0, default_return_value=True)
    assert extcall IERC20(constants.CVX_TOKEN).approve(
        VAULT_RELAYER, max_value(uint256), default_return_value=True
    )


@internal
def _swap(
    _caller: address,
    _min_amount_out: uint256,
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
    _tokens: DynArray[address, constants.MAX_TOKENS],
    _buy_amounts: DynArray[uint256, constants.MAX_TOKENS],
) -> uint256:
    """
    @notice Submit multiple token swaps to a single target token
    @param _caller Address to receive caller fee
    @param _min_amount_out Minimum amount expected from final swap to target asset
    @param _reward_hook_calldata Calldata to pass to extra reward hook contract
    @param _target_hook_calldata Calldata to pass to target hook contract
    @param _tokens Array of tokens to sell
    @param _buy_amounts Array of minimum buy amounts for each token
    @return target_asset_balance Amount of target asset received
    """

    assert len(_tokens) > 0, "No tokens provided"
    assert len(_tokens) == len(_buy_amounts), "Arrays length mismatch"


    # if a hook contract is set to handle extra rewards, we call it
    if swapper.extra_reward_hook != empty(address):
        raw_call(
            swapper.extra_reward_hook,
            _reward_hook_calldata,
            value=0,
        )

    for i: uint256 in range(constants.MAX_TOKENS):
        if i == len(_tokens):
            break
        if not self.token_orders[_tokens[i]]:
            extcall IComposableCoW(COMPOSABLE_COW).create(
                ConditionalOrderParams(
                    handler=self,
                    salt=empty(bytes32),
                    staticInput=concat(b"", convert(_tokens[i], bytes20)),
                ),
                True,
            )
            self.token_orders[_tokens[i]] = True
            # in case we want to process extra rewards with CoW rather than hook, we set approvals here
            if _tokens[i] not in [constants.CVX_TOKEN, constants.CRV_TOKEN]:
                assert extcall IERC20(_tokens[i]).approve(
                    VAULT_RELAYER, 0, default_return_value=True
                )
                assert extcall IERC20(_tokens[i]).approve(
                    VAULT_RELAYER, max_value(uint256), default_return_value=True
                )

        # Check if order has expired
        # If no order exists and last_order_time is 0, this will also create an entry
        if self.token_order_info[_tokens[i]].last_order_time + self.delay <= block.timestamp:
            current_balance: uint256 = staticcall IERC20(_tokens[i]).balanceOf(self)
            self.token_order_info[_tokens[i]] = TokenOrderInfo(
                last_order_time=block.timestamp,
                buy_amount=_buy_amounts[i],
                sell_amount=current_balance,
            )

    # If no rewards were swapped, we end early
    crvusd_available: uint256 = staticcall IERC20(constants.CRVUSD_TOKEN).balanceOf(self)
    if crvusd_available == 0:
        return 0

    platform_fee: uint256 = staticcall IStrategy(swapper.strategy).platform_fee()
    treasury: address = swapper._treasury()
    swapper._collect_fee(treasury, constants.CRVUSD_TOKEN, crvusd_available, platform_fee)

    # Pay the caller incentive in crvUSD
    caller_fee: uint256 = staticcall IStrategy(swapper.strategy).caller_fee()
    swapper._collect_fee(_caller, constants.CRVUSD_TOKEN, crvusd_available, caller_fee)

    # if we have a hook contract to handle further operations
    if swapper.target_hook != empty(address):
        raw_call(
            swapper.target_hook,
            _target_hook_calldata,
            value=0,
        )

    target_asset: address = staticcall IStrategy(swapper.strategy).asset()
    target_asset_balance: uint256 = staticcall IERC20(target_asset).balanceOf(self)
    assert target_asset_balance > _min_amount_out, "Slippage"
    assert extcall IERC20(target_asset).transfer(
        swapper.strategy,
        target_asset_balance,
        default_return_value=True,
    )
    return target_asset_balance


@external
@view
def getTradeableOrder(
    _owner: address,
    _sender: address,
    _ctx: bytes32,
    _static_input: Bytes[20],
    _offchain_input: Bytes[1],
) -> GPv2OrderData:
    """
    @notice Generate a tradeable order
    @dev This is called by watch-towers to get executable orders
    @param _owner The owner of the conditional order
    @param _sender `msg.sender` context calling `isValidSignature`
    @param _ctx Execution context - Not used
    @param _static_input Conditional order type-specific data known
            at time of creation for all discrete orders - sell token
            address as bytes20
    @param _offchain_input Conditional order type-specific data NOT
            known at time of creation for a specific discrete order
            (or zero-length bytes if not applicable) - Not used
    @return Order parameters
    """
    sell_token: address = convert(convert(_static_input, bytes20), address)
    order: GPv2OrderData = self._create_order(sell_token)
    sell_balance: uint256 = staticcall IERC20(sell_token).balanceOf(self)
    if sell_balance == 0:
        raw_revert(
            abi_encode(
                block.timestamp + (DAY),
                "Nothing to swap",
                method_id=method_id("PollTryAtEpoch(uint256,string)"),
            )
        )
    if self.token_order_info[sell_token].last_order_time + self.delay <= block.timestamp:
        raw_revert(
            abi_encode(
                block.timestamp + (DAY),
                "Order expired",
                method_id=method_id("PollTryAtEpoch(uint256,string)"),
            )
        )
    return order


@internal
@view
def _verify(
    _owner: address,
    _sender: address,
    _hash: bytes32,
    _domain_separator: bytes32,
    _ctx: bytes32,
    _static_input: Bytes[20],
    _offchain_input: Bytes[1],
    _order: GPv2OrderData,
):
    """
    @notice Verify that a proposed order matches our conditions
    @dev This is called by ComposableCoW to validate orders
    """
    sell_token: address = convert(convert(_static_input, bytes20), address)
    if not self.token_orders[sell_token]:
        raw_revert(abi_encode("Wrong token", method_id=method_id("OrderNotValid(string)")))

    expected_order: GPv2OrderData = self._create_order(sell_token)
    expected_order.sellAmount = _order.sellAmount
    expected_order.buyAmount = max(_order.buyAmount, expected_order.buyAmount)
    if abi_encode(expected_order) != abi_encode(_order):
        raw_revert(abi_encode("Invalid order", method_id=method_id("OrderNotValid(string)")))


@external
@view
def verify(
    _owner: address,
    _sender: address,
    _hash: bytes32,
    _domain_separator: bytes32,
    _ctx: bytes32,
    _static_input: Bytes[20],
    _offchain_input: Bytes[1],
    _order: GPv2OrderData,
):
    """
    @notice Verify that a proposed order matches our conditions
    @dev This is called by ComposableCoW to validate orders
    """
    self._verify(
        _owner,
        _sender,
        _hash,
        _domain_separator,
        _ctx,
        _static_input,
        _offchain_input,
        _order,
    )


@internal
@view
def _create_order(_token: address) -> GPv2OrderData:
    return GPv2OrderData(
        sellToken=_token,
        buyToken=constants.CRVUSD_TOKEN,
        receiver=self,
        sellAmount=self.token_order_info[_token].sell_amount,
        buyAmount=self.token_order_info[_token].buy_amount,
        validTo=convert(self.token_order_info[_token].last_order_time + self.delay, uint32),
        appData=APP_DATA,
        feeAmount=0,
        kind=ORDER_KIND_SELL,
        partiallyFillable=False,
        sellTokenBalance=BALANCE_ERC20,
        buyTokenBalance=BALANCE_ERC20,
    )


@external
@view
def isValidSignature(_hash: bytes32, _signature: Bytes[2048]) -> bytes4:
    """
    @notice Validate a signature according to ERC-1271
    @dev Called by CoW Protocol to validate orders
    @param _hash The hash that was signed
    @param _signature The signature data (encoded GPv2OrderData)
    @return Magic value if signature is valid
    """
    # Decode the signature as GPv2OrderData
    order: GPv2OrderData = empty(GPv2OrderData)
    payload: Payload = empty(Payload)
    order, payload = abi_decode(_signature, (GPv2OrderData, Payload))

    # Verify the order using existing verify logic
    # Extract static input from order (assuming sellToken is the static input)
    static_input: Bytes[20] = concat(b"", convert(order.sellToken, bytes20))
    domain_separator: bytes32 = staticcall IComposableCoW(COMPOSABLE_COW).domainSeparator()
    self._verify(
        msg.sender,  # owner
        msg.sender,  # _sender
        _hash,  # _hash
        empty(bytes32),  # _domain_separator
        empty(bytes32),  # _ctx
        static_input,  # _static_input
        b"",  # _offchain_input
        order,  # _order
    )

    return staticcall IComposableCoW(COMPOSABLE_COW).isValidSafeSignature(
        self,
        msg.sender,
        _hash,
        staticcall IComposableCoW(COMPOSABLE_COW).domainSeparator(),
        empty(bytes32),
        abi_encode(order),
        abi_encode(payload),
    )


@external
@pure
def supportsInterface(_interface_id: bytes4) -> bool:
    """
    @notice Check if this contract supports a given interface
    @dev Required for ERC-165 compliance
    @param _interface_id The interface identifier to check
    """
    # Avoid InvalidFallbackHandler error in ComposableCow and switch to EIP-1271
    assert _interface_id != SIGNATURE_VERIFIER_MUXER_INTERFACE
    return _interface_id in SUPPORTED_INTERFACES


@external
def cancel_order(_token: address):
    """
    @notice Cancel a conditional order for a specific token
    @param _token The token whose order should be cancelled
    @dev Only callable by harvest manager
    """
    vault: IVault = IVault(staticcall IStrategy(swapper.strategy).vault())
    assert staticcall vault.hasRole(staticcall vault.HARVESTER_ROLE(), msg.sender), "Manager only"

    assert self.token_orders[_token], "No order exists"

    order_params: ConditionalOrderParams = ConditionalOrderParams(
        handler=self,
        salt=empty(bytes32),
        staticInput=concat(b"", convert(_token, bytes20)),
    )

    order_hash: bytes32 = staticcall IComposableCoW(COMPOSABLE_COW).hash(order_params)

    extcall IComposableCoW(COMPOSABLE_COW).remove(order_hash)
    self.token_orders[_token] = False
    self.token_order_info[_token] = TokenOrderInfo(last_order_time=0, buy_amount=0, sell_amount=0)

    log ConditionalOrderCancelled(token=_token, hash=order_hash)


@external
@view
def get_order_info(_token: address) -> (bool, TokenOrderInfo):
    """
    @notice Get order information for a token
    @param _token The token to query
    @return exists Whether an order exists for this token
    @return info The order information
    """
    return self.token_orders[_token], self.token_order_info[_token]
