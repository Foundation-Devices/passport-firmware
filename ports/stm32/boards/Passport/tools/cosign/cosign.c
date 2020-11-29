// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#include <libgen.h>
#include <time.h>

#ifdef USE_CRYPTO
#include <openssl/bio.h>
#include <openssl/ec.h>
#endif /* USE_CRYPTO */

#include "fwheader.h"
#include "hash.h"
#ifdef USE_CRYPTO
#include "firmware-keys.h"
#include "uECC.h"
#endif /* USE_CRYPTO */

#define EXTENSION   "-signed"

static char *firmware;
static char *version;
static bool help;
static bool debug_log_level;
static bool extract_signature;
static uint8_t header[FW_HEADER_SIZE];
#ifdef USE_CRYPTO
static char *key;

extern EC_KEY *PEM_read_bio_ECPrivateKey(BIO *bp, EC_KEY **key, void *cb, void *u);
#endif /* USE_CRYPTO */
static void usage(
    char *name
)
{
    printf("Usage:%s\n", name);
    printf("\t-d: debug logging\n"
           "\t-f <firmware file>: full path to firmware file to sign\n"
           "\t-h: this message"
#ifdef USE_CRYPTO
           "\t-k <private key filey>\n"
#endif /* USE_CRYPTO */
           "\t-v <version>: firmware version\n"
          );
    exit(1);
}

static void process_args(
    int argc,
    char **argv
)
{
    int c = 0;

#ifdef USE_CRYPTO
    while ((c = getopt(argc, argv, "dhf:v:k:x")) != -1)
#else
    while ((c = getopt(argc, argv, "dhf:v:x")) != -1)
#endif /* USE_CRYPTO */
    {
        switch (c)
        {
            case 'f':
                firmware = optarg;
            break;
            case 'v':
                version = optarg;
            break;
#ifdef USE_CRYPTO
            case 'k':
                key = optarg;
            break;
#endif /* USE_CRYPTO */
            case 'd':
                debug_log_level = true;
            break;
             case 'h':
                help = true;
            break;
            case 'x':
                extract_signature = true;
            break;
            default:
                usage(argv[0]);
            break;
        }
    }
}

static size_t read_file(
    char *path,
    uint8_t **buffer
)
{
    uint32_t ret = 0;
    struct stat info;
    FILE *fp;

    fp = fopen(path, "r");
    if (fp == NULL)
    {
        printf("failed to open %s\n", path);
        return 0;
    }

    stat(path, &info);
    *buffer = (uint8_t*)calloc(1, info.st_size + sizeof(ulong));
    if (*buffer == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }

    ret = fread(*buffer, 1, info.st_size, fp);
    if (ret != info.st_size)
        free(*buffer);
    else
        ret = info.st_size;

out:
    fclose(fp);
    return ret;
}

static uint8_t *read_private_key(
    char *key
)
{
    BIO *in;
    EC_KEY *eckey;
    const BIGNUM *pkey;
    int len;
    int keylen;
    uint8_t *private_key = NULL;

    in = BIO_new_file(key, "r");
    if (in == NULL)
    {
        printf("key %s does not appear to be in PEM format\n", key);
        return NULL;
    }

    eckey = PEM_read_bio_ECPrivateKey(in, NULL, NULL, NULL);
    if (eckey == NULL)
    {
        printf("could not read key %s\n", key);
        goto out;
    }

    pkey = EC_KEY_get0_private_key(eckey);
    if (pkey == NULL)
    {
        printf("internal error: could not get binary from private key %s\n", key);
        goto out;
    }

    len = BN_num_bytes(pkey);
    if (len <= 0)
    {
        printf("could not get private key length: %d\n", len);
        goto out;
    }

    private_key = (uint8_t *)calloc(1, len);
    if (private_key == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }

    keylen = BN_bn2bin(pkey, private_key);
    if (keylen != len)
    {
        printf("could not convert private key %s\n", key);
        goto out;
    }

out:
    BIO_free(in);
    return private_key;
}

static uint8_t *read_public_key(
    char *key
)
{
    BIO *in;
    BN_CTX *ctx;
    EC_KEY *eckey;
    const EC_GROUP *ecgroup;
    const EC_POINT *ecpoint;
    BIGNUM *pkeyx;
    BIGNUM *pkeyy;
    uint8_t *x;
    uint8_t *y;
    int rc;
    int lenx;
    int leny;
    int keylen;
    uint8_t *public_key = NULL;

    in = BIO_new_file(key, "r");
    if (in == NULL)
    {
        printf("key %s does not appear to be in PEM format\n", key);
        return NULL;
    }

    eckey = PEM_read_bio_ECPrivateKey(in, NULL, NULL, NULL);
    if (eckey == NULL)
    {
        printf("could not read key %s\n", key);
        goto out;
    }

    ctx = BN_CTX_new();
    if (ctx == NULL)
    {
        printf("could not get BN context\n");
        goto out;
    }
    pkeyx = BN_new();
    if (pkeyx == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }
    pkeyy = BN_new();
    if (pkeyy == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }
    ecgroup = EC_KEY_get0_group(eckey);
    if (ecgroup == NULL)
    {
        printf("failed to get EC GROUP\n");
        goto out;
    }
    ecpoint = EC_KEY_get0_public_key(eckey);
    if (ecpoint == NULL)
    {
        printf("failed to get public key from private key\n");
        goto out;
    }
    rc = EC_POINT_get_affine_coordinates(ecgroup, ecpoint, pkeyx, pkeyy, ctx);
    if (rc == 0)
    {
        printf("get affine failed\n");
        goto out;
    }
    lenx = BN_num_bytes(pkeyx);
    if (lenx <= 0)
    {
        printf("invalid public key length: %d\n", lenx);
        goto out;
    }
    leny = BN_num_bytes(pkeyy);
    if (leny <= 0)
    {
        printf("invalid public key length: %d\n", leny);
        goto out;
    }
    x = (uint8_t *)calloc(1, lenx);
    if (x == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }
    y = (uint8_t *)calloc(1, leny);
    if (y == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }
    public_key = (uint8_t *)calloc(1, lenx + leny);
    if (public_key == NULL)
    {
        printf("insufficient memory\n");
        goto out;
    }
    keylen = BN_bn2bin(pkeyx, x);
    if (keylen != lenx)
    {
        printf("could not convert public key %s\n", key);
        goto out;
    }
    keylen = BN_bn2bin(pkeyy, y);
    if (keylen != leny)
    {
        printf("could not convert public key %s\n", key);
        goto out;
    }

    memcpy(public_key, x, lenx);
    memcpy(&public_key[lenx], y, leny);
    BN_CTX_free(ctx);
    BN_free(pkeyx);
    BN_free(pkeyy);

out:
    BIO_free(in);
    return public_key;
}

int find_public_key(
    uint8_t *key
)
{
    int keynum;

    for (keynum = 0; keynum < FW_MAX_PUB_KEYS; ++keynum)
    {
        if (memcmp(approved_pubkeys[keynum], key, sizeof(approved_pubkeys[keynum])) == 0)
            return keynum;
    }
    return -1;
}

static void sign_firmware(
    char *fw,
#ifdef USE_CRYPTO
    char *key,
#endif /* USE_CRYPTO */
    char *version
)
{
    int rc;
    size_t ret = 0;
    size_t fwlen;
    uint8_t *fwbuf = NULL;
    FILE *fp = NULL;
    char *output = NULL;
    char *path;
    char *filename;
    char *file;
    char *tmp;
    passport_firmware_header_t *hdrptr;
    uint8_t *fwptr;
    uint8_t fw_hash[HASH_LEN];
    uint8_t *working_signature;
#ifdef USE_CRYPTO
    uint8_t working_key = 0;
    uint8_t *private_key;
    uint8_t *public_key;
#endif /* USE_CRYPTO */
    if (fw == NULL)
    {
        printf("firmware not specified\n");
        return;
    }
#ifdef USE_CRYPTO
    if (key == NULL)
    {
        printf("private key not specified\n");
        return;
    }

    private_key = read_private_key(key);
    if (private_key == NULL)
    {
        printf("could not get private key\n");
        return;
    }    

    public_key = read_public_key(key);
    if (public_key == NULL)
    {
        printf("could not get public key\n");
        return;
    }    

    rc = find_public_key(public_key);
    if (rc < 0)
    {
        printf("key %s does not have a supported public key\n", key);
        return;
    }    
    else
        working_key = rc;
#endif /* USE_CRYPTO */
    tmp = strdup(fw);

    filename = basename(tmp);
    if (filename == NULL)
    {
        printf("basename() failed\n");
        return;
    }

    path = dirname(tmp);
    if (path == NULL)
    {
        printf("dirname() failed\n");
        return;
    }

    file = strtok(filename, ".");
    if (file == NULL)
    {
        printf("strtok() failed\n");
        return;
    }

    output = (char *)calloc(1, strlen(fw) + strlen(EXTENSION) + 1);
    if (output == NULL)
    {
        printf("insufficient memory\n");
        return;
    }

    sprintf(output, "%s/%s%s.bin", path, file, EXTENSION);

    if (debug_log_level)
        printf("Reading %s...", fw);
    fwlen = read_file(fw, &fwbuf);
    if (fwlen == 0)
    {
        printf("file %s has no data\n", fw);
        return;
    }
    if (debug_log_level)
        printf("done\n");

    fp = fopen(output, "wb");
    if (fp == NULL)
    {
        printf("failed to open %s\n", output);
        goto out;
    }

    /*
     * Test for an existing header in the firwmare. I one exists that
     * means that it has been signed at least once already.
     */
    hdrptr = (passport_firmware_header_t *)fwbuf;
    if (hdrptr->info.magic == FW_HEADER_MAGIC)
    {
        /* Looks like there is an existing header...let's validate it */
        if (hdrptr->info.timestamp == 0)
        {
            printf("Existing header found but timestamp invalid\n");
            goto out;
        }
        else if (strlen((char *)hdrptr->info.fwversion) == 0)
        {
            printf("Existing header found but FW version invalid\n");
            goto out;
        }
        else if (hdrptr->info.fwlength != fwlen - FW_HEADER_SIZE)
        {
            printf("Existing header found but FW length invalid\n");
            goto out;
        }
#ifdef USE_CRYPTO
        else if (hdrptr->signature.pubkey1 == working_key)
        {
            printf("Existing header found but specified key matches the first public key\n");
            goto out;
        }

        hdrptr->signature.pubkey2 = working_key;
#endif /* USE_CRYPTO */
        working_signature = hdrptr->signature.signature2;
        fwptr = fwbuf + FW_HEADER_SIZE;
    }
    else
    {
        /* No existing header...confirm that the user specified a version */
        if (version == NULL)
        {
            printf("version not specified\n");
            goto out;
        }

        hdrptr = (passport_firmware_header_t *)header;

        /* Create a new header...this is the first signature. */
        hdrptr->info.magic = FW_HEADER_MAGIC;
        hdrptr->info.timestamp = time(NULL);
        strcpy((char *)hdrptr->info.fwversion, version);
        hdrptr->info.fwlength = fwlen;
#ifdef USE_CRYPTO
        hdrptr->signature.pubkey1 = working_key;
#endif /* USE_CRYPTO */
        working_signature = hdrptr->signature.signature1;
        fwptr = fwbuf;
    }

    if (debug_log_level)
    {
        printf("FW header content:\n");
        printf("\ttimestamp: %d\n",   hdrptr->info.timestamp);
        printf("\tfwversion: %s\n",   hdrptr->info.fwversion);
        printf("\t fwlength: %d\n",   hdrptr->info.fwlength);
    }

    hash_fw(&hdrptr->info, fwptr, hdrptr->info.fwlength, fw_hash, HASH_LEN);

    if (debug_log_level)
    {
        printf("FW hash: ");
        for (int i = 0; i < HASH_LEN; ++i)
            printf("%02x", fw_hash[i]);
        printf("\n");
    }
#ifdef USE_CRYPTO
    /* Encrypt the hash here... */
    rc = uECC_sign(private_key,
                   fw_hash, sizeof(fw_hash),
                   working_signature, uECC_secp256k1());
    if (rc == 0)
    {
        printf("signature failed\n");
        goto out;
    }

    rc = uECC_verify(approved_pubkeys[working_key],
                     fw_hash, sizeof(fw_hash),
                     working_signature, uECC_secp256k1());
    if (rc == 0)
    {
        printf("verify signature failed\n");
        goto out;
    }
#else
    memset(working_signature, 0, SIGNATURE_LEN);
    memcpy(working_signature, fw_hash, HASH_LEN);
#endif /* USE_CRYPTO */
    if (debug_log_level)
    {
        printf("signature: ");
        for (int i = 0; i < SIGNATURE_LEN; ++i)
            printf("%02x", working_signature[i]);
        printf("\n");
    }

    if (debug_log_level)
        printf("Writing header to %s - ", output);
    ret = fwrite(hdrptr, 1, FW_HEADER_SIZE, fp);
    if (ret != FW_HEADER_SIZE)
    {
        unlink(output);
        printf("\n%s write failed - check disk space\n", output);
        goto out;
    }
    if (debug_log_level)
        printf("done\n");

    if (debug_log_level)
        printf("Writing firmware to %s - ", output);
    ret = fwrite(fwptr, 1, hdrptr->info.fwlength, fp);
    if (ret != hdrptr->info.fwlength)
    {
        unlink(output);
        printf("\n%s write failed - check disk space\n", output);
        goto out;
    }
    if (debug_log_level)
        printf("done\n");

out:
    free(fwbuf);
    free(output);
    free(tmp);
    fclose(fp);
}

static void dump_firmware_signature(
    char *fw
)
{
    size_t fwlen;
    uint8_t *fwbuf = NULL;
    passport_firmware_header_t *hdrptr;

    if (fw == NULL)
    {
        printf("firmware not specified\n");
        return;
    }

    if (debug_log_level)
        printf("Reading %s...", fw);
    fwlen = read_file(fw, &fwbuf);
    if (fwlen == 0)
    {
        printf("file %s has no data\n", fw);
        return;
    }
    if (debug_log_level)
        printf("done\n");

    hdrptr = (passport_firmware_header_t *)fwbuf;
    if (hdrptr->info.magic == FW_HEADER_MAGIC)
    {
        printf("FW header content:\n");
        printf("\ttimestamp: %d\n",   hdrptr->info.timestamp);
        printf("\tfwversion: %s\n",   hdrptr->info.fwversion);
        printf("\t fwlength: %d\n",   hdrptr->info.fwlength);
        printf("\t      key: %d\n",   hdrptr->signature.pubkey1);
        printf("\tsignature: ");
        for (int i = 0; i < SIGNATURE_LEN; ++i)
            printf("%02x", hdrptr->signature.signature1[i]);
        printf("\n");
        printf("\t      key: %d\n",   hdrptr->signature.pubkey2);
        printf("\tsignature: ");
        for (int i = 0; i < SIGNATURE_LEN; ++i)
            printf("%02x", hdrptr->signature.signature2[i]);
        printf("\n");
    }
    else
        printf("No firmware header found in file %s\n", fw);
}

int main(int argc, char *argv[])
{
    process_args(argc, argv);

    if (help)
        usage(argv[0]);

    if (extract_signature)
        dump_firmware_signature(firmware);
    else
#ifdef USE_CRYPTO
        sign_firmware(firmware, key, version);
#else
        sign_firmware(firmware, version);
#endif /* USE_CRYPTO */

    exit(0);
}
