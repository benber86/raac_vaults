# pragma version 0.4.3
# @license MIT

@internal
@pure
def uint_to_str5(_number: uint256) -> String[5]:
    """
    @notice Turns a 5 or less digit uint256 into its string representation
    @dev We use this to cast the result of a uint2str built-in to
         a String[5] and truncate it if needed, as convert() won't
         automatically truncate and slice() won't pad the string if
         it's too short.
         https://github.com/vyperlang/vyper/issues/4685
    @param _number The number to convert
    """

    str_number: String[78] = uint2str(_number)
    if len(str_number) > 5:
        return slice(str_number, 0, 5)
    else:
        return convert(str_number, String[5])
