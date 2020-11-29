"""
This is an auxiliary script that is used to compute valid PLL values to set
the CPU frequency to a given value.  The algorithm here appears as C code
for the machine.freq() function.
"""

from __future__ import print_function
import re

def close_int(x):
    return abs(x - round(x)) < 0.01

# original version that requires N/M to be an integer (for simplicity)
def compute_pll(hse, sys):
    for P in (2, 4, 6, 8): # allowed values of P
        Q = sys * P / 48
        NbyM = sys * P / hse
        # N/M and Q must be integers
        if not (close_int(NbyM) and close_int(Q)):
            continue
        # VCO_OUT must be between 192MHz and 432MHz
        if not (192 <= hse * NbyM <= 432):
            continue
        # compute M
        M = int(192 // NbyM)
        while hse > 2 * M or NbyM * M < 192:
            M += 1
        # VCO_IN must be between 1MHz and 2MHz (2MHz recommended)
        if not (M <= hse):
            continue
        # compute N
        N = NbyM * M
        # N and Q are restricted
        if not (192 <= N <= 432 and 2 <= Q <= 15):
            continue
        # found valid values
        assert NbyM == N // M
        return (M, N, P, Q)
    # no valid values found
    return None

# improved version that doesn't require N/M to be an integer
def compute_pll2(hse, sys, relax_pll48):
    # Loop over the allowed values of P, looking for a valid PLL configuration
    # that gives the desired "sys" frequency.  We use floats for P to force
    # floating point arithmetic on Python 2.
    fallback = None
    for P in (2.0, 4.0, 6.0, 8.0):
        NbyM = sys * P / hse
        # VCO_OUT must be between 192MHz and 432MHz
        if not (192 <= hse * NbyM <= 432):
            continue
        # scan M
        M = int(192 // NbyM) # starting value
        while 2 * M < hse:
            M += 1
        # VCO_IN must be between 1MHz and 2MHz (2MHz recommended)
        for M in range(M, hse + 1):
            if NbyM * M < 191.99 or not close_int(NbyM * M):
                continue
            # compute N
            N = NbyM * M
            # N must be an integer
            if not close_int(N):
                continue
            # N is restricted
            if not (192 <= N <= 432):
                continue
            Q = (sys * P / 48)
            # Q must be an integer in a set range
            if not (2 <= Q <= 15):
                continue
            if not close_int(Q):
                if int(M) == int(hse) and fallback is None:
                    # the values don't give 48MHz on PLL48 but are otherwise OK
                    fallback = M, N, P, int(Q)
                continue
            # found valid values
            return (M, N, P, Q)
    if relax_pll48:
        # might have found values which don't give 48MHz on PLL48
        return fallback
    else:
        # no valid values found which give 48MHz on PLL48
        return None

def compute_derived(hse, pll):
    M, N, P, Q = pll
    vco_in = hse / M
    vco_out = hse * N / M
    pllck = hse / M * N / P
    pll48ck = hse / M * N / Q
    return (vco_in, vco_out, pllck, pll48ck)

def verify_pll(hse, pll):
    M, N, P, Q = pll
    vco_in, vco_out, pllck, pll48ck = compute_derived(hse, pll)

    # verify ints
    assert close_int(M)
    assert close_int(N)
    assert close_int(P)
    assert close_int(Q)

    # verify range
    assert 2 <= M <= 63
    assert 192 <= N <= 432
    assert P in (2, 4, 6, 8)
    assert 2 <= Q <= 15
    assert 1 <= vco_in <= 2
    assert 192 <= vco_out <= 432

def compute_pll_table(source_clk, relax_pll48):
    valid_plls = []
    for sysclk in range(2, 217, 2):
        pll = compute_pll2(source_clk, sysclk, relax_pll48)
        if pll is not None:
            verify_pll(source_clk, pll)
            valid_plls.append((sysclk, pll))
    return valid_plls

def generate_c_table(hse, valid_plls):
    valid_plls.sort()
    print("// (M, P/2-1, SYS) values for %u MHz source" % hse)
    print("static const uint16_t pll_freq_table[%u] = {" % len(valid_plls))
    for sys, (M, N, P, Q) in valid_plls:
        print("    (%u << 10) | (%u << 8) | %u," % (M, P // 2 - 1, sys))
    print("};")

def print_table(hse, valid_plls):
    print("HSE =", hse, "MHz")
    print("sys :  M      N     P     Q : VCO_IN VCO_OUT   PLLCK PLL48CK")
    out_format = "%3u : %2u  %.1f  %.2f  %.2f :  %5.2f  %6.2f  %6.2f  %6.2f"
    for sys, pll in valid_plls:
        print(out_format % ((sys,) + pll + compute_derived(hse, pll)))
    print("found %u valid configurations" % len(valid_plls))

def search_header_for_hsx_values(filename, vals):
    regex_inc = re.compile(r'#include "(boards/[A-Za-z0-9_./]+)"')
    regex_def = re.compile(r'#define +(HSE_VALUE|HSI_VALUE) +\((\(uint32_t\))?([0-9]+)\)')
    with open(filename) as f:
        for line in f:
            line = line.strip()
            m = regex_inc.match(line)
            if m:
                # Search included file
                search_header_for_hsx_values(m.group(1), vals)
                continue
            m = regex_def.match(line)
            if m:
                # Found HSE_VALUE or HSI_VALUE
                val = int(m.group(3)) // 1000000
                if m.group(1) == 'HSE_VALUE':
                    vals[0] = val
                else:
                    vals[1] = val
    return vals

def main():
    global out_format

    # parse input args
    import sys
    argv = sys.argv[1:]

    c_table = False
    relax_pll48 = False
    hse = None
    hsi = None

    while True:
        if argv[0] == '-c':
            c_table = True
            argv.pop(0)
        elif argv[0] == '--relax-pll48':
            relax_pll48 = True
            argv.pop(0)
        else:
            break

    if len(argv) != 1:
        print("usage: pllvalues.py [-c] <hse in MHz>")
        sys.exit(1)

    if argv[0].startswith("file:"):
        # extract HSE_VALUE, and optionally HSI_VALUE, from header file
        hse, hsi = search_header_for_hsx_values(argv[0][5:], [None, None])
        if hse is None:
            raise ValueError("%s does not contain a definition of HSE_VALUE" % argv[0])
        if hsi is not None and hsi > 16:
            # Currently, a HSI value greater than 16MHz is not supported
            hsi = None
    else:
        # HSE given directly as an integer
        hse = int(argv[0])

    hse_valid_plls = compute_pll_table(hse, relax_pll48)
    if hsi is not None:
        hsi_valid_plls = compute_pll_table(hsi, relax_pll48)

    if c_table:
        print('#if MICROPY_HW_CLK_USE_HSI')
        if hsi is not None:
            hsi_valid_plls.append((hsi, (0, 0, 2, 0)))
            generate_c_table(hsi, hsi_valid_plls)
        print('#else')
        if hsi is not None:
            hse_valid_plls.append((hsi, (0, 0, 2, 0)))
        hse_valid_plls.append((hse, (1, 0, 2, 0)))
        generate_c_table(hse, hse_valid_plls)
        print('#endif')
    else:
        print_table(hse, hse_valid_plls)

if __name__ == "__main__":
    main()
