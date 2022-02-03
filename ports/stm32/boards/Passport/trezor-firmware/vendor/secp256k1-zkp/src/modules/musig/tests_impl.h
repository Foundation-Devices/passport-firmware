/**********************************************************************
 * Copyright (c) 2018 Andrew Poelstra                                 *
 * Distributed under the MIT software license, see the accompanying   *
 * file COPYING or http://www.opensource.org/licenses/mit-license.php.*
 **********************************************************************/

#ifndef _SECP256K1_MODULE_MUSIG_TESTS_
#define _SECP256K1_MODULE_MUSIG_TESTS_

#include "secp256k1_musig.h"

int secp256k1_xonly_pubkey_create(secp256k1_xonly_pubkey *pk, const unsigned char *seckey) {
    int ret;
    secp256k1_keypair keypair;
    ret = secp256k1_keypair_create(ctx, &keypair, seckey);
    ret &= secp256k1_keypair_xonly_pub(ctx, pk, NULL, &keypair);
    return ret;
}

/* Just a simple (non-adaptor, non-tweaked) 2-of-2 MuSig combine, sign, verify
 * test. */
void musig_simple_test(secp256k1_scratch_space *scratch) {
    unsigned char sk[2][32];
    secp256k1_musig_session session[2];
    secp256k1_musig_session_signer_data signer0[2];
    secp256k1_musig_session_signer_data signer1[2];
    unsigned char nonce_commitment[2][32];
    unsigned char msg[32];
    secp256k1_xonly_pubkey combined_pk;
    secp256k1_musig_pre_session pre_session;
    unsigned char session_id[2][32];
    secp256k1_xonly_pubkey pk[2];
    const secp256k1_xonly_pubkey *pk_ptr[2];
    const unsigned char *ncs[2];
    unsigned char public_nonce[3][32];
    secp256k1_musig_partial_signature partial_sig[2];
    unsigned char final_sig[64];

    secp256k1_testrand256(session_id[0]);
    secp256k1_testrand256(session_id[1]);
    secp256k1_testrand256(sk[0]);
    secp256k1_testrand256(sk[1]);
    secp256k1_testrand256(msg);

    pk_ptr[0] = &pk[0];
    pk_ptr[1] = &pk[1];
    CHECK(secp256k1_xonly_pubkey_create(&pk[0], sk[0]) == 1);
    CHECK(secp256k1_xonly_pubkey_create(&pk[1], sk[1]) == 1);

    CHECK(secp256k1_musig_pubkey_combine(ctx, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    CHECK(secp256k1_musig_session_init(ctx, &session[1], signer1, nonce_commitment[1], session_id[1], msg, &combined_pk, &pre_session, 2, sk[1]) == 1);
    CHECK(secp256k1_musig_session_init(ctx, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 1);

    ncs[0] = nonce_commitment[0];
    ncs[1] = nonce_commitment[1];

    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session[0], signer0, public_nonce[0], ncs, 2, NULL) == 1);
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session[1], signer1, public_nonce[1], ncs, 2, NULL) == 1);

    CHECK(secp256k1_musig_set_nonce(ctx, &signer0[0], public_nonce[0]) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signer0[1], public_nonce[1]) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signer1[0], public_nonce[0]) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signer1[1], public_nonce[1]) == 1);

    CHECK(secp256k1_musig_session_combine_nonces(ctx, &session[0], signer0, 2, NULL, NULL) == 1);
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &session[1], signer1, 2, NULL, NULL) == 1);

    CHECK(secp256k1_musig_partial_sign(ctx, &session[0], &partial_sig[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[0], &signer0[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sign(ctx, &session[1], &partial_sig[1]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[0], &signer0[1], &partial_sig[1], &pk[1]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[1], &signer1[1], &partial_sig[1], &pk[1]) == 1);

    CHECK(secp256k1_musig_partial_sig_combine(ctx, &session[0], final_sig, partial_sig, 2) == 1);
    CHECK(secp256k1_schnorrsig_verify(ctx, final_sig, msg, sizeof(msg), &combined_pk) == 1);
}

void musig_api_tests(secp256k1_scratch_space *scratch) {
    secp256k1_scratch_space *scratch_small;
    secp256k1_musig_session session[2];
    secp256k1_musig_session session_uninitialized;
    secp256k1_musig_session verifier_session;
    secp256k1_musig_session_signer_data signer0[2];
    secp256k1_musig_session_signer_data signer1[2];
    secp256k1_musig_session_signer_data verifier_signer_data[2];
    secp256k1_musig_partial_signature partial_sig[2];
    secp256k1_musig_partial_signature partial_sig_adapted[2];
    secp256k1_musig_partial_signature partial_sig_overflow;
    unsigned char final_sig[64];
    unsigned char final_sig_cmp[64];

    unsigned char buf[32];
    unsigned char sk[2][32];
    unsigned char ones[32];
    unsigned char session_id[2][32];
    unsigned char nonce_commitment[2][32];
    int combined_nonce_parity;
    const unsigned char *ncs[2];
    unsigned char msg[32];
    secp256k1_xonly_pubkey combined_pk;
    secp256k1_musig_pre_session pre_session;
    secp256k1_musig_pre_session pre_session_uninitialized;
    secp256k1_xonly_pubkey pk[2];
    const secp256k1_xonly_pubkey *pk_ptr[2];
    secp256k1_xonly_pubkey invalid_pk;
    const secp256k1_xonly_pubkey *invalid_pk_ptr2[2];
    const secp256k1_xonly_pubkey *invalid_pk_ptr3[3];
    unsigned char tweak[32];

    unsigned char sec_adaptor[32];
    unsigned char sec_adaptor1[32];
    secp256k1_pubkey adaptor;
    int i;

    /** setup **/
    secp256k1_context *none = secp256k1_context_create(SECP256K1_CONTEXT_NONE);
    secp256k1_context *sign = secp256k1_context_create(SECP256K1_CONTEXT_SIGN);
    secp256k1_context *vrfy = secp256k1_context_create(SECP256K1_CONTEXT_VERIFY);
    int ecount;

    secp256k1_context_set_error_callback(none, counting_illegal_callback_fn, &ecount);
    secp256k1_context_set_error_callback(sign, counting_illegal_callback_fn, &ecount);
    secp256k1_context_set_error_callback(vrfy, counting_illegal_callback_fn, &ecount);
    secp256k1_context_set_illegal_callback(none, counting_illegal_callback_fn, &ecount);
    secp256k1_context_set_illegal_callback(sign, counting_illegal_callback_fn, &ecount);
    secp256k1_context_set_illegal_callback(vrfy, counting_illegal_callback_fn, &ecount);

    memset(ones, 0xff, 32);
    /* Simulate structs being uninitialized by setting it to 0s. We don't want
     * to produce undefined behavior by actually providing uninitialized
     * structs. */
    memset(&pre_session_uninitialized, 0, sizeof(pre_session_uninitialized));
    memset(&session_uninitialized, 0, sizeof(session_uninitialized));
    memset(&invalid_pk, 0, sizeof(invalid_pk));

    secp256k1_testrand256(session_id[0]);
    secp256k1_testrand256(session_id[1]);
    secp256k1_testrand256(sk[0]);
    secp256k1_testrand256(sk[1]);
    secp256k1_testrand256(msg);
    secp256k1_testrand256(sec_adaptor);
    secp256k1_testrand256(tweak);

    pk_ptr[0] = &pk[0];
    pk_ptr[1] = &pk[1];
    CHECK(secp256k1_xonly_pubkey_create(&pk[0], sk[0]) == 1);
    CHECK(secp256k1_xonly_pubkey_create(&pk[1], sk[1]) == 1);
    CHECK(secp256k1_ec_pubkey_create(ctx, &adaptor, sec_adaptor) == 1);

    for (i = 0; i < 2; i++) {
        invalid_pk_ptr2[i] = &invalid_pk;
        invalid_pk_ptr3[i] = &pk[i];
    }
    /* invalid_pk_ptr3 has two valid, one invalid pk, which is important to test
     * musig_pubkeys_combine */
    invalid_pk_ptr3[2] = &invalid_pk;

    /** main test body **/

    /* Key combination */
    ecount = 0;
    CHECK(secp256k1_musig_pubkey_combine(none, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    CHECK(secp256k1_musig_pubkey_combine(sign, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    /* pubkey_combine does not require a scratch space */
    CHECK(secp256k1_musig_pubkey_combine(vrfy, NULL, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    /* A small scratch space works too, but will result in using an ineffecient algorithm */
    scratch_small = secp256k1_scratch_space_create(ctx, 1);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch_small, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    secp256k1_scratch_space_destroy(ctx, scratch_small);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, NULL, &pre_session, pk_ptr, 2) == 0);
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, NULL, pk_ptr, 2) == 1);
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, NULL, 2) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, invalid_pk_ptr2, 2) == 0);
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, invalid_pk_ptr3, 3) == 0);
    CHECK(ecount == 4);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, pk_ptr, 0) == 0);
    CHECK(ecount == 5);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, NULL, 0) == 0);
    CHECK(ecount == 6);

    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);
    CHECK(secp256k1_musig_pubkey_combine(vrfy, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);

    /** Tweaking */
    ecount = 0;
    {
        secp256k1_xonly_pubkey tmp_internal_pk = combined_pk;
        secp256k1_pubkey tmp_output_pk;
        secp256k1_musig_pre_session tmp_pre_session = pre_session;
        CHECK(secp256k1_musig_pubkey_tweak_add(ctx, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, tweak) == 1);
        /* Reset pre_session */
        tmp_pre_session = pre_session;
        CHECK(secp256k1_musig_pubkey_tweak_add(none, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, tweak) == 1);
        tmp_pre_session = pre_session;
        CHECK(secp256k1_musig_pubkey_tweak_add(sign, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, tweak) == 1);
        tmp_pre_session = pre_session;
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, tweak) == 1);
        tmp_pre_session = pre_session;
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, NULL, &tmp_output_pk, &tmp_internal_pk, tweak) == 0);
        CHECK(ecount == 1);
        /* Uninitialized pre_session */
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &pre_session_uninitialized, &tmp_output_pk, &tmp_internal_pk, tweak) == 0);
        CHECK(ecount == 2);
        /* Using the same pre_session twice does not work */
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, tweak) == 1);
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, tweak) == 0);
        CHECK(ecount == 3);
        tmp_pre_session = pre_session;
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &tmp_pre_session, NULL, &tmp_internal_pk, tweak) == 0);
        CHECK(ecount == 4);
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &tmp_pre_session, &tmp_output_pk, NULL, tweak) == 0);
        CHECK(ecount == 5);
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, NULL) == 0);
        CHECK(ecount == 6);
        CHECK(secp256k1_musig_pubkey_tweak_add(vrfy, &tmp_pre_session, &tmp_output_pk, &tmp_internal_pk, ones) == 0);
        CHECK(ecount == 6);
    }

    /** Session creation **/
    ecount = 0;
    CHECK(secp256k1_musig_session_init(none, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 0);
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_session_init(vrfy, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 1);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_session_init(sign, NULL, signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 0);
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_session_init(sign, &session[0], NULL, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 0);
    CHECK(ecount == 4);
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, NULL, session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 0);
    CHECK(ecount == 5);
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], NULL, msg, &combined_pk, &pre_session, 2, sk[0]) == 0);
    CHECK(ecount == 6);
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], NULL, &combined_pk, &pre_session, 2, sk[0]) == 1);
    CHECK(ecount == 6);
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, NULL, &pre_session, 2, sk[0]) == 0);
    CHECK(ecount == 7);
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, NULL, 2, sk[0]) == 0);
    CHECK(ecount == 8);
    /* Uninitialized pre_session */
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session_uninitialized, 2, sk[0]) == 0);
    CHECK(ecount == 9);
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 0, sk[0]) == 0);
    CHECK(ecount == 10);
    /* If more than UINT32_MAX fits in a size_t, test that session_init
     * rejects n_signers that high. */
    if (SIZE_MAX > UINT32_MAX) {
        CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, ((size_t) UINT32_MAX) + 2, sk[0]) == 0);
        CHECK(ecount == 11);
    } else {
        ecount = 11;
    }
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, NULL) == 0);
    CHECK(ecount == 12);
    /* secret key overflows */
    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, ones) == 0);
    CHECK(ecount == 12);

    CHECK(secp256k1_musig_session_init(sign, &session[0], signer0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 1);
    CHECK(secp256k1_musig_session_init(sign, &session[1], signer1, nonce_commitment[1], session_id[1], msg, &combined_pk, &pre_session, 2, sk[1]) == 1);
    ncs[0] = nonce_commitment[0];
    ncs[1] = nonce_commitment[1];

    ecount = 0;
    CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, msg, &combined_pk, &pre_session, ncs, 2) == 1);
    CHECK(ecount == 0);
    CHECK(secp256k1_musig_session_init_verifier(none, NULL, verifier_signer_data, msg, &combined_pk, &pre_session, ncs, 2) == 0);
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, NULL, &combined_pk, &pre_session, ncs, 2) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, msg, NULL, &pre_session, ncs, 2) == 0);
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, msg, &combined_pk, NULL, ncs, 2) == 0);
    CHECK(ecount == 4);
    CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, msg, &combined_pk, &pre_session, NULL, 2) == 0);
    CHECK(ecount == 5);
    CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, msg, &combined_pk, &pre_session, ncs, 0) == 0);
    CHECK(ecount == 6);
    if (SIZE_MAX > UINT32_MAX) {
        CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, msg, &combined_pk, &pre_session, ncs, ((size_t) UINT32_MAX) + 2) == 0);
        CHECK(ecount == 7);
    } else {
        ecount = 7;
    }
    CHECK(secp256k1_musig_session_init_verifier(none, &verifier_session, verifier_signer_data, msg, &combined_pk, &pre_session, ncs, 2) == 1);

    /** Signing step 0 -- exchange nonce commitments */
    ecount = 0;
    {
        unsigned char nonce[32];
        secp256k1_musig_session session_0_tmp;

        memcpy(&session_0_tmp, &session[0], sizeof(session_0_tmp));

        /* Can obtain public nonce after commitments have been exchanged; still can't sign */
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session_0_tmp, signer0, nonce, ncs, 2, NULL) == 1);
        CHECK(secp256k1_musig_partial_sign(none, &session_0_tmp, &partial_sig[0]) == 0);
        CHECK(ecount == 1);
    }

    /** Signing step 1 -- exchange nonces */
    ecount = 0;
    {
        unsigned char public_nonce[3][32];
        secp256k1_musig_session session_0_tmp;

        memcpy(&session_0_tmp, &session[0], sizeof(session_0_tmp));
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session_0_tmp, signer0, public_nonce[0], ncs, 2, NULL) == 1);
        CHECK(ecount == 0);
        /* Reset session */
        memcpy(&session_0_tmp, &session[0], sizeof(session_0_tmp));
        CHECK(secp256k1_musig_session_get_public_nonce(none, NULL, signer0, public_nonce[0], ncs, 2, NULL) == 0);
        CHECK(ecount == 1);
        /* uninitialized session */
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session_uninitialized, signer0, public_nonce[0], ncs, 2, NULL) == 0);
        CHECK(ecount == 2);
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session_0_tmp, NULL, public_nonce[0], ncs, 2, NULL) == 0);
        CHECK(ecount == 3);
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session_0_tmp, signer0, NULL, ncs, 2, NULL) == 0);
        CHECK(ecount == 4);
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session_0_tmp, signer0, public_nonce[0], NULL, 2, NULL) == 0);
        CHECK(ecount == 5);
        /* Number of commitments and number of signers are different */
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session_0_tmp, signer0, public_nonce[0], ncs, 1, NULL) == 0);
        CHECK(ecount == 6);

        CHECK(secp256k1_musig_session_get_public_nonce(none, &session[0], signer0, public_nonce[0], ncs, 2, NULL) == 1);
        CHECK(secp256k1_musig_session_get_public_nonce(none, &session[1], signer1, public_nonce[1], ncs, 2, NULL) == 1);

        CHECK(secp256k1_musig_set_nonce(none, &signer0[0], public_nonce[0]) == 1);
        CHECK(secp256k1_musig_set_nonce(none, &signer0[1], public_nonce[0]) == 0);
        CHECK(secp256k1_musig_set_nonce(none, &signer0[1], public_nonce[1]) == 1);
        CHECK(secp256k1_musig_set_nonce(none, &signer0[1], public_nonce[1]) == 1);
        CHECK(ecount == 6);

        CHECK(secp256k1_musig_set_nonce(none, NULL, public_nonce[0]) == 0);
        CHECK(ecount == 7);
        CHECK(secp256k1_musig_set_nonce(none, &signer1[0], NULL) == 0);
        CHECK(ecount == 8);

        CHECK(secp256k1_musig_set_nonce(none, &signer1[0], public_nonce[0]) == 1);
        CHECK(secp256k1_musig_set_nonce(none, &signer1[1], public_nonce[1]) == 1);
        CHECK(secp256k1_musig_set_nonce(none, &verifier_signer_data[0], public_nonce[0]) == 1);
        CHECK(secp256k1_musig_set_nonce(none, &verifier_signer_data[1], public_nonce[1]) == 1);

        ecount = 0;
        memcpy(&session_0_tmp, &session[0], sizeof(session_0_tmp));
        CHECK(secp256k1_musig_session_combine_nonces(none, &session_0_tmp, signer0, 2, &combined_nonce_parity, &adaptor) == 1);
        memcpy(&session_0_tmp, &session[0], sizeof(session_0_tmp));
        CHECK(secp256k1_musig_session_combine_nonces(none, NULL, signer0, 2, &combined_nonce_parity, &adaptor) == 0);
        CHECK(ecount == 1);
        /* Uninitialized session */
        CHECK(secp256k1_musig_session_combine_nonces(none, &session_uninitialized, signer0, 2, &combined_nonce_parity, &adaptor) == 0);
        CHECK(ecount == 2);
        CHECK(secp256k1_musig_session_combine_nonces(none, &session_0_tmp, NULL, 2, &combined_nonce_parity, &adaptor) == 0);
        CHECK(ecount == 3);
        /* Number of signers differs from number during intialization */
        CHECK(secp256k1_musig_session_combine_nonces(none, &session_0_tmp, signer0, 1, &combined_nonce_parity, &adaptor) == 0);
        CHECK(ecount == 4);
        CHECK(secp256k1_musig_session_combine_nonces(none, &session_0_tmp, signer0, 2, NULL, &adaptor) == 1);
        CHECK(ecount == 4);
        memcpy(&session_0_tmp, &session[0], sizeof(session_0_tmp));
        CHECK(secp256k1_musig_session_combine_nonces(none, &session_0_tmp, signer0, 2, &combined_nonce_parity, NULL) == 1);

        CHECK(secp256k1_musig_session_combine_nonces(none, &session[0], signer0, 2, &combined_nonce_parity, &adaptor) == 1);
        CHECK(secp256k1_musig_session_combine_nonces(none, &session[1], signer0, 2, &combined_nonce_parity, &adaptor) == 1);
        CHECK(secp256k1_musig_session_combine_nonces(none, &verifier_session, verifier_signer_data, 2, &combined_nonce_parity, &adaptor) == 1);
    }

    /** Signing step 2 -- partial signatures */
    ecount = 0;
    CHECK(secp256k1_musig_partial_sign(none, &session[0], &partial_sig[0]) == 1);
    CHECK(ecount == 0);
    CHECK(secp256k1_musig_partial_sign(none, NULL, &partial_sig[0]) == 0);
    CHECK(ecount == 1);
    /* Uninitialized session */
    CHECK(secp256k1_musig_partial_sign(none, &session_uninitialized, &partial_sig[0]) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_partial_sign(none, &session[0], NULL) == 0);
    CHECK(ecount == 3);

    CHECK(secp256k1_musig_partial_sign(none, &session[0], &partial_sig[0]) == 1);
    CHECK(secp256k1_musig_partial_sign(none, &session[1], &partial_sig[1]) == 1);
    /* observer can't sign */
    CHECK(secp256k1_musig_partial_sign(none, &verifier_session, &partial_sig[2]) == 0);
    CHECK(ecount == 4);

    ecount = 0;
    CHECK(secp256k1_musig_partial_signature_serialize(none, buf, &partial_sig[0]) == 1);
    CHECK(secp256k1_musig_partial_signature_serialize(none, NULL, &partial_sig[0]) == 0);
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_partial_signature_serialize(none, buf, NULL) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_partial_signature_parse(none, &partial_sig[0], buf) == 1);
    CHECK(secp256k1_musig_partial_signature_parse(none, NULL, buf) == 0);
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_partial_signature_parse(none, &partial_sig[0], NULL) == 0);
    CHECK(ecount == 4);
    CHECK(secp256k1_musig_partial_signature_parse(none, &partial_sig_overflow, ones) == 1);

    /** Partial signature verification */
    ecount = 0;
    CHECK(secp256k1_musig_partial_sig_verify(none, &session[0], &signer0[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(sign, &session[0], &signer0[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], &signer0[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], &signer0[0], &partial_sig[1], &pk[0]) == 0);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, NULL, &signer0[0], &partial_sig[0], &pk[0]) == 0);
    CHECK(ecount == 1);
    /* Unitialized session */
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session_uninitialized, &signer0[0], &partial_sig[0], &pk[0]) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], NULL, &partial_sig[0], &pk[0]) == 0);
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], &signer0[0], NULL, &pk[0]) == 0);
    CHECK(ecount == 4);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], &signer0[0], &partial_sig_overflow, &pk[0]) == 0);
    CHECK(ecount == 4);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], &signer0[0], &partial_sig[0], NULL) == 0);
    CHECK(ecount == 5);

    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], &signer0[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[1], &signer1[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[0], &signer0[1], &partial_sig[1], &pk[1]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &session[1], &signer1[1], &partial_sig[1], &pk[1]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &verifier_session, &verifier_signer_data[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(vrfy, &verifier_session, &verifier_signer_data[1], &partial_sig[1], &pk[1]) == 1);
    CHECK(ecount == 5);

    /** Adaptor signature verification */
    memcpy(&partial_sig_adapted[1], &partial_sig[1], sizeof(partial_sig_adapted[1]));
    ecount = 0;
    CHECK(secp256k1_musig_partial_sig_adapt(none, &partial_sig_adapted[0], &partial_sig[0], sec_adaptor, combined_nonce_parity) == 1);
    CHECK(secp256k1_musig_partial_sig_adapt(none, NULL, &partial_sig[0], sec_adaptor, 0) == 0);
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_partial_sig_adapt(none, &partial_sig_adapted[0], NULL, sec_adaptor, 0) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_partial_sig_adapt(none, &partial_sig_adapted[0], &partial_sig_overflow, sec_adaptor, combined_nonce_parity) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_partial_sig_adapt(none, &partial_sig_adapted[0], &partial_sig[0], NULL, 0) == 0);
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_partial_sig_adapt(none, &partial_sig_adapted[0], &partial_sig[0], ones, combined_nonce_parity) == 0);
    CHECK(ecount == 3);

    /** Signing combining and verification */
    ecount = 0;
    CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], final_sig, partial_sig_adapted, 2) == 1);
    CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], final_sig_cmp, partial_sig_adapted, 2) == 1);
    CHECK(memcmp(final_sig, final_sig_cmp, sizeof(final_sig)) == 0);
    CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], final_sig_cmp, partial_sig_adapted, 2) == 1);
    CHECK(memcmp(final_sig, final_sig_cmp, sizeof(final_sig)) == 0);

    CHECK(secp256k1_musig_partial_sig_combine(none, NULL, final_sig, partial_sig_adapted, 2) == 0);
    CHECK(ecount == 1);
    /* Unitialized session */
    CHECK(secp256k1_musig_partial_sig_combine(none, &session_uninitialized, final_sig, partial_sig_adapted, 2) == 0);
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], NULL, partial_sig_adapted, 2) == 0);
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], final_sig, NULL, 2) == 0);
    CHECK(ecount == 4);
    {
        secp256k1_musig_partial_signature partial_sig_tmp[2];
        partial_sig_tmp[0] = partial_sig_adapted[0];
        partial_sig_tmp[1] = partial_sig_overflow;
        CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], final_sig, partial_sig_tmp, 2) == 0);
    }
    CHECK(ecount == 4);
    /* Wrong number of partial sigs */
    CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], final_sig, partial_sig_adapted, 1) == 0);
    CHECK(ecount == 4);
    CHECK(secp256k1_musig_partial_sig_combine(none, &session[0], final_sig, partial_sig_adapted, 2) == 1);
    CHECK(ecount == 4);

    CHECK(secp256k1_schnorrsig_verify(vrfy, final_sig, msg, sizeof(msg), &combined_pk) == 1);

    /** Secret adaptor can be extracted from signature */
    ecount = 0;
    CHECK(secp256k1_musig_extract_secret_adaptor(none, sec_adaptor1, final_sig, partial_sig, 2, combined_nonce_parity) == 1);
    CHECK(memcmp(sec_adaptor, sec_adaptor1, 32) == 0);
    CHECK(secp256k1_musig_extract_secret_adaptor(none, NULL, final_sig, partial_sig, 2, 0) == 0);
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_extract_secret_adaptor(none, sec_adaptor1, NULL, partial_sig, 2, 0) == 0);
    CHECK(ecount == 2);
    {
        unsigned char final_sig_tmp[64];
        memcpy(final_sig_tmp, final_sig, sizeof(final_sig_tmp));
        memcpy(&final_sig_tmp[32], ones, 32);
        CHECK(secp256k1_musig_extract_secret_adaptor(none, sec_adaptor1, final_sig_tmp, partial_sig, 2, combined_nonce_parity) == 0);
    }
    CHECK(ecount == 2);
    CHECK(secp256k1_musig_extract_secret_adaptor(none, sec_adaptor1, final_sig, NULL, 2, 0) == 0);
    CHECK(ecount == 3);
    {
        secp256k1_musig_partial_signature partial_sig_tmp[2];
        partial_sig_tmp[0] = partial_sig[0];
        partial_sig_tmp[1] = partial_sig_overflow;
        CHECK(secp256k1_musig_extract_secret_adaptor(none, sec_adaptor1, final_sig, partial_sig_tmp, 2, combined_nonce_parity) == 0);
    }
    CHECK(ecount == 3);
    CHECK(secp256k1_musig_extract_secret_adaptor(none, sec_adaptor1, final_sig, partial_sig, 0, 0) == 1);
    CHECK(secp256k1_musig_extract_secret_adaptor(none, sec_adaptor1, final_sig, partial_sig, 2, 1) == 1);

    /** cleanup **/
    memset(&session, 0, sizeof(session));
    secp256k1_context_destroy(none);
    secp256k1_context_destroy(sign);
    secp256k1_context_destroy(vrfy);
}

/* Initializes two sessions, one use the given parameters (session_id,
 * nonce_commitments, etc.) except that `session_tmp` uses new signers with different
 * public keys. The point of this test is to call `musig_session_get_public_nonce`
 * with signers from `session_tmp` who have different public keys than the correct
 * ones and return the resulting messagehash. This should not result in a different
 * messagehash because the public keys of the signers are only used during session
 * initialization. */
void musig_state_machine_diff_signer_msghash_test(unsigned char *msghash, secp256k1_xonly_pubkey *pks, secp256k1_xonly_pubkey *combined_pk, secp256k1_musig_pre_session *pre_session, const unsigned char * const *nonce_commitments, unsigned char *msg, unsigned char *nonce_other, unsigned char *sk, unsigned char *session_id) {
    secp256k1_musig_session session;
    secp256k1_musig_session session_tmp;
    unsigned char nonce_commitment[32];
    secp256k1_musig_session_signer_data signers[2];
    secp256k1_musig_session_signer_data signers_tmp[2];
    unsigned char sk_dummy[32];
    secp256k1_xonly_pubkey pks_tmp[2];
    const secp256k1_xonly_pubkey *pks_tmp_ptr[2];
    secp256k1_xonly_pubkey combined_pk_tmp;
    secp256k1_musig_pre_session pre_session_tmp;
    unsigned char nonce[32];

    /* Set up signers with different public keys */
    secp256k1_testrand256(sk_dummy);
    pks_tmp[0] = pks[0];
    CHECK(secp256k1_xonly_pubkey_create(&pks_tmp[1], sk_dummy) == 1);
    pks_tmp_ptr[0] = &pks_tmp[0];
    pks_tmp_ptr[1] = &pks_tmp[1];
    CHECK(secp256k1_musig_pubkey_combine(ctx, NULL, &combined_pk_tmp, &pre_session_tmp, pks_tmp_ptr, 2) == 1);
    CHECK(secp256k1_musig_session_init(ctx, &session_tmp, signers_tmp, nonce_commitment, session_id, msg, &combined_pk_tmp, &pre_session_tmp, 2, sk_dummy) == 1);

    CHECK(secp256k1_musig_session_init(ctx, &session, signers, nonce_commitment, session_id, msg, combined_pk, pre_session, 2, sk) == 1);
    CHECK(memcmp(nonce_commitment, nonce_commitments[1], 32) == 0);
    /* Call get_public_nonce with different signers than the signers the session was
     * initialized with. */
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session_tmp, signers, nonce, nonce_commitments, 2, NULL) == 1);
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session, signers_tmp, nonce, nonce_commitments, 2, NULL) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers[0], nonce_other) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers[1], nonce) == 1);
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &session, signers, 2, NULL, NULL) == 1);

    secp256k1_musig_compute_messagehash(ctx, msghash, &session);
}

/* Creates a new session (with a different session id) and tries to use that session
 * to combine nonces with given signers_other. This should fail, because the nonce
 * commitments of signers_other do not match the nonce commitments the new session
 * was initialized with. If do_test is 0, the correct signers are being used and
 * therefore the function should return 1. */
int musig_state_machine_diff_signers_combine_nonce_test(secp256k1_xonly_pubkey *combined_pk, secp256k1_musig_pre_session *pre_session, unsigned char *nonce_commitment_other, unsigned char *nonce_other, unsigned char *msg, unsigned char *sk, secp256k1_musig_session_signer_data *signers_other, int do_test) {
    secp256k1_musig_session session;
    secp256k1_musig_session_signer_data signers[2];
    secp256k1_musig_session_signer_data *signers_to_use;
    unsigned char nonce_commitment[32];
    unsigned char session_id[32];
    unsigned char nonce[32];
    const unsigned char *ncs[2];

    /* Initialize new signers */
    secp256k1_testrand256(session_id);
    CHECK(secp256k1_musig_session_init(ctx, &session, signers, nonce_commitment, session_id, msg, combined_pk, pre_session, 2, sk) == 1);
    ncs[0] = nonce_commitment_other;
    ncs[1] = nonce_commitment;
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session, signers, nonce, ncs, 2, NULL) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers[0], nonce_other) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers[1], nonce) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers[1], nonce) == 1);
    secp256k1_musig_session_combine_nonces(ctx, &session, signers_other, 2, NULL, NULL);
    if (do_test) {
        signers_to_use = signers_other;
    } else {
        signers_to_use = signers;
    }
    return secp256k1_musig_session_combine_nonces(ctx, &session, signers_to_use, 2, NULL, NULL);
}

/* Initializaes a session with the given session_id, signers, pk, msg etc.
 * parameters but without a message. Will test that the message must be
 * provided with `get_public_nonce`.
 */
void musig_state_machine_late_msg_test(secp256k1_xonly_pubkey *pks, secp256k1_xonly_pubkey *combined_pk, secp256k1_musig_pre_session *pre_session, unsigned char *nonce_commitment_other, unsigned char *nonce_other, unsigned char *sk, unsigned char *session_id, unsigned char *msg) {
    /* Create context for testing ARG_CHECKs by setting an illegal_callback. */
    secp256k1_context *ctx_tmp = secp256k1_context_create(SECP256K1_CONTEXT_NONE);
    int ecount = 0;
    secp256k1_musig_session session;
    secp256k1_musig_session_signer_data signers[2];
    unsigned char nonce_commitment[32];
    const unsigned char *ncs[2];
    unsigned char nonce[32];
    secp256k1_musig_partial_signature partial_sig;

    secp256k1_context_set_illegal_callback(ctx_tmp, counting_illegal_callback_fn, &ecount);
    CHECK(secp256k1_musig_session_init(ctx, &session, signers, nonce_commitment, session_id, NULL, combined_pk, pre_session, 2, sk) == 1);
    ncs[0] = nonce_commitment_other;
    ncs[1] = nonce_commitment;

    /* Trying to get the nonce without providing a message fails. */
    CHECK(ecount == 0);
    CHECK(secp256k1_musig_session_get_public_nonce(ctx_tmp, &session, signers, nonce, ncs, 2, NULL) == 0);
    CHECK(ecount == 1);

    /* Providing a message should make get_public_nonce succeed. */
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session, signers, nonce, ncs, 2, msg) == 1);
    /* Trying to set the message again fails. */
    CHECK(ecount == 1);
    CHECK(secp256k1_musig_session_get_public_nonce(ctx_tmp, &session, signers, nonce, ncs, 2, msg) == 0);
    CHECK(ecount == 2);

    /* Check that it's working */
    CHECK(secp256k1_musig_set_nonce(ctx, &signers[0], nonce_other) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers[1], nonce) == 1);
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &session, signers, 2, NULL, NULL) == 1);
    CHECK(secp256k1_musig_partial_sign(ctx, &session, &partial_sig));
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &session, &signers[1], &partial_sig, &pks[1]));
    secp256k1_context_destroy(ctx_tmp);
}

void musig_state_machine_tests(secp256k1_scratch_space *scratch) {
    secp256k1_context *ctx_tmp = secp256k1_context_create(SECP256K1_CONTEXT_VERIFY | SECP256K1_CONTEXT_VERIFY);
    size_t i;
    secp256k1_musig_session session[2];
    secp256k1_musig_session_signer_data signers0[2];
    secp256k1_musig_session_signer_data signers1[2];
    unsigned char nonce_commitment[2][32];
    unsigned char session_id[2][32];
    unsigned char msg[32];
    unsigned char sk[2][32];
    secp256k1_xonly_pubkey pk[2];
    const secp256k1_xonly_pubkey *pk_ptr[2];
    secp256k1_xonly_pubkey combined_pk;
    secp256k1_musig_pre_session pre_session;
    unsigned char nonce[2][32];
    const unsigned char *ncs[2];
    secp256k1_musig_partial_signature partial_sig[2];
    unsigned char sig[64];
    unsigned char msghash1[32];
    unsigned char msghash2[32];
    int ecount;

    secp256k1_context_set_illegal_callback(ctx_tmp, counting_illegal_callback_fn, &ecount);
    ecount = 0;

    /* Run state machine with the same objects twice to test that it's allowed to
     * reinitialize session and session_signer_data. */
    for (i = 0; i < 2; i++) {
        /* Setup */
        secp256k1_testrand256(session_id[0]);
        secp256k1_testrand256(session_id[1]);
        secp256k1_testrand256(sk[0]);
        secp256k1_testrand256(sk[1]);
        secp256k1_testrand256(msg);
        pk_ptr[0] = &pk[0];
        pk_ptr[1] = &pk[1];
        CHECK(secp256k1_xonly_pubkey_create(&pk[0], sk[0]) == 1);
        CHECK(secp256k1_xonly_pubkey_create(&pk[1], sk[1]) == 1);
        CHECK(secp256k1_musig_pubkey_combine(ctx, scratch, &combined_pk, &pre_session, pk_ptr, 2) == 1);
        CHECK(secp256k1_musig_session_init(ctx, &session[0], signers0, nonce_commitment[0], session_id[0], msg, &combined_pk, &pre_session, 2, sk[0]) == 1);
        CHECK(secp256k1_musig_session_init(ctx, &session[1], signers1, nonce_commitment[1], session_id[1], msg, &combined_pk, &pre_session, 2, sk[1]) == 1);
        /* Can't combine nonces unless we're through round 1 already */
        ecount = 0;
        CHECK(secp256k1_musig_session_combine_nonces(ctx_tmp, &session[0], signers0, 2, NULL, NULL) == 0);
        CHECK(ecount == 1);

        /* Set nonce commitments */
        ncs[0] = nonce_commitment[0];
        ncs[1] = nonce_commitment[1];
        CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session[0], signers0, nonce[0], ncs, 2, NULL) == 1);
        /* Calling the function again is not okay */
        ecount = 0;
        CHECK(secp256k1_musig_session_get_public_nonce(ctx_tmp, &session[0], signers0, nonce[0], ncs, 2, NULL) == 0);
        CHECK(ecount == 1);

        /* Get nonce for signer 1 */
        CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session[1], signers1, nonce[1], ncs, 2, NULL) == 1);

        /* Set nonces */
        CHECK(secp256k1_musig_set_nonce(ctx, &signers0[0], nonce[0]) == 1);
        /* Can't set nonce that doesn't match nonce commitment */
        CHECK(secp256k1_musig_set_nonce(ctx, &signers0[1], nonce[0]) == 0);
        /* Set correct nonce */
        CHECK(secp256k1_musig_set_nonce(ctx, &signers0[1], nonce[1]) == 1);

        /* Combine nonces */
        CHECK(secp256k1_musig_session_combine_nonces(ctx, &session[0], signers0, 2, NULL, NULL) == 1);
        /* Not everyone is present from signer 1's view */
        CHECK(secp256k1_musig_session_combine_nonces(ctx, &session[1], signers1, 2, NULL, NULL) == 0);
        /* Make everyone present */
        CHECK(secp256k1_musig_set_nonce(ctx, &signers1[0], nonce[0]) == 1);
        CHECK(secp256k1_musig_set_nonce(ctx, &signers1[1], nonce[1]) == 1);

        /* Can't combine nonces from signers of a different session */
        CHECK(musig_state_machine_diff_signers_combine_nonce_test(&combined_pk, &pre_session, nonce_commitment[0], nonce[0], msg, sk[1], signers1, 1) == 0);
        CHECK(musig_state_machine_diff_signers_combine_nonce_test(&combined_pk, &pre_session, nonce_commitment[0], nonce[0], msg, sk[1], signers1, 0) == 1);

        /* Partially sign */
        CHECK(secp256k1_musig_partial_sign(ctx, &session[0], &partial_sig[0]) == 1);
        /* Can't verify, sign or combine signatures until nonce is combined */
        ecount = 0;
        CHECK(secp256k1_musig_partial_sig_verify(ctx_tmp, &session[1], &signers1[0], &partial_sig[0], &pk[0]) == 0);
        CHECK(ecount == 1);
        CHECK(secp256k1_musig_partial_sign(ctx_tmp, &session[1], &partial_sig[1]) == 0);
        CHECK(ecount == 2);
        memset(&partial_sig[1], 0, sizeof(partial_sig[1]));
        CHECK(secp256k1_musig_partial_sig_combine(ctx_tmp, &session[1], sig, partial_sig, 2) == 0);
        CHECK(ecount == 3);

        CHECK(secp256k1_musig_session_combine_nonces(ctx, &session[1], signers1, 2, NULL, NULL) == 1);
        CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[1], &signers1[0], &partial_sig[0], &pk[0]) == 1);
        /* messagehash should be the same as a session whose get_public_nonce was called
         * with different signers (i.e. they diff in public keys). This is because the
         * public keys of the signers is set in stone when initializing the session. */
        secp256k1_musig_compute_messagehash(ctx, msghash1, &session[1]);
        musig_state_machine_diff_signer_msghash_test(msghash2, pk, &combined_pk, &pre_session, ncs, msg, nonce[0], sk[1], session_id[1]);
        CHECK(memcmp(msghash1, msghash2, 32) == 0);
        CHECK(secp256k1_musig_partial_sign(ctx, &session[1], &partial_sig[1]) == 1);

        CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[1], &signers1[1], &partial_sig[1], &pk[1]) == 1);
        /* Wrong signature */
        CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[1], &signers1[1], &partial_sig[0], &pk[1]) == 0);
        /* Can't get the public nonce until msg is set */
        musig_state_machine_late_msg_test(pk, &combined_pk, &pre_session, nonce_commitment[0], nonce[0], sk[1], session_id[1], msg);
    }
    secp256k1_context_destroy(ctx_tmp);
}

void scriptless_atomic_swap(secp256k1_scratch_space *scratch) {
    /* Throughout this test "a" and "b" refer to two hypothetical blockchains,
     * while the indices 0 and 1 refer to the two signers. Here signer 0 is
     * sending a-coins to signer 1, while signer 1 is sending b-coins to signer
     * 0. Signer 0 produces the adaptor signatures. */
    unsigned char final_sig_a[64];
    unsigned char final_sig_b[64];
    secp256k1_musig_partial_signature partial_sig_a[2];
    secp256k1_musig_partial_signature partial_sig_b_adapted[2];
    secp256k1_musig_partial_signature partial_sig_b[2];
    unsigned char sec_adaptor[32];
    unsigned char sec_adaptor_extracted[32];
    secp256k1_pubkey pub_adaptor;

    unsigned char seckey_a[2][32];
    unsigned char seckey_b[2][32];
    secp256k1_xonly_pubkey pk_a[2];
    const secp256k1_xonly_pubkey *pk_a_ptr[2];
    secp256k1_xonly_pubkey pk_b[2];
    const secp256k1_xonly_pubkey *pk_b_ptr[2];
    secp256k1_musig_pre_session pre_session_a;
    secp256k1_musig_pre_session pre_session_b;
    secp256k1_xonly_pubkey combined_pk_a;
    secp256k1_xonly_pubkey combined_pk_b;
    secp256k1_musig_session musig_session_a[2];
    secp256k1_musig_session musig_session_b[2];
    unsigned char noncommit_a[2][32];
    unsigned char noncommit_b[2][32];
    const unsigned char *noncommit_a_ptr[2];
    const unsigned char *noncommit_b_ptr[2];
    unsigned char pubnon_a[2][32];
    unsigned char pubnon_b[2][32];
    int combined_nonce_parity_a;
    int combined_nonce_parity_b;
    secp256k1_musig_session_signer_data data_a[2];
    secp256k1_musig_session_signer_data data_b[2];

    const unsigned char seed[32] = "still tired of choosing seeds...";
    const unsigned char msg32_a[32] = "this is the message blockchain a";
    const unsigned char msg32_b[32] = "this is the message blockchain b";

    /* Step 1: key setup */
    secp256k1_testrand256(seckey_a[0]);
    secp256k1_testrand256(seckey_a[1]);
    secp256k1_testrand256(seckey_b[0]);
    secp256k1_testrand256(seckey_b[1]);
    secp256k1_testrand256(sec_adaptor);

    pk_a_ptr[0] = &pk_a[0];
    pk_a_ptr[1] = &pk_a[1];
    pk_b_ptr[0] = &pk_b[0];
    pk_b_ptr[1] = &pk_b[1];
    CHECK(secp256k1_xonly_pubkey_create(&pk_a[0], seckey_a[0]));
    CHECK(secp256k1_xonly_pubkey_create(&pk_a[1], seckey_a[1]));
    CHECK(secp256k1_xonly_pubkey_create(&pk_b[0], seckey_b[0]));
    CHECK(secp256k1_xonly_pubkey_create(&pk_b[1], seckey_b[1]));
    CHECK(secp256k1_ec_pubkey_create(ctx, &pub_adaptor, sec_adaptor));

    CHECK(secp256k1_musig_pubkey_combine(ctx, scratch, &combined_pk_a, &pre_session_a, pk_a_ptr, 2));
    CHECK(secp256k1_musig_pubkey_combine(ctx, scratch, &combined_pk_b, &pre_session_b, pk_b_ptr, 2));

    CHECK(secp256k1_musig_session_init(ctx, &musig_session_a[0], data_a, noncommit_a[0], seed, msg32_a, &combined_pk_a, &pre_session_a, 2, seckey_a[0]));
    CHECK(secp256k1_musig_session_init(ctx, &musig_session_a[1], data_a, noncommit_a[1], seed, msg32_a, &combined_pk_a, &pre_session_a, 2, seckey_a[1]));
    noncommit_a_ptr[0] = noncommit_a[0];
    noncommit_a_ptr[1] = noncommit_a[1];

    CHECK(secp256k1_musig_session_init(ctx, &musig_session_b[0], data_b, noncommit_b[0], seed, msg32_b, &combined_pk_b, &pre_session_b, 2, seckey_b[0]));
    CHECK(secp256k1_musig_session_init(ctx, &musig_session_b[1], data_b, noncommit_b[1], seed, msg32_b, &combined_pk_b, &pre_session_b, 2, seckey_b[1]));
    noncommit_b_ptr[0] = noncommit_b[0];
    noncommit_b_ptr[1] = noncommit_b[1];

    /* Step 2: Exchange nonces */
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &musig_session_a[0], data_a, pubnon_a[0], noncommit_a_ptr, 2, NULL));
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &musig_session_a[1], data_a, pubnon_a[1], noncommit_a_ptr, 2, NULL));
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &musig_session_b[0], data_b, pubnon_b[0], noncommit_b_ptr, 2, NULL));
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &musig_session_b[1], data_b, pubnon_b[1], noncommit_b_ptr, 2, NULL));
    CHECK(secp256k1_musig_set_nonce(ctx, &data_a[0], pubnon_a[0]));
    CHECK(secp256k1_musig_set_nonce(ctx, &data_a[1], pubnon_a[1]));
    CHECK(secp256k1_musig_set_nonce(ctx, &data_b[0], pubnon_b[0]));
    CHECK(secp256k1_musig_set_nonce(ctx, &data_b[1], pubnon_b[1]));
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &musig_session_a[0], data_a, 2, &combined_nonce_parity_a, &pub_adaptor));
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &musig_session_a[1], data_a, 2, NULL, &pub_adaptor));
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &musig_session_b[0], data_b, 2, &combined_nonce_parity_b, &pub_adaptor));
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &musig_session_b[1], data_b, 2, NULL, &pub_adaptor));

    /* Step 3: Signer 0 produces partial signatures for both chains. */
    CHECK(secp256k1_musig_partial_sign(ctx, &musig_session_a[0], &partial_sig_a[0]));
    CHECK(secp256k1_musig_partial_sign(ctx, &musig_session_b[0], &partial_sig_b[0]));

    /* Step 4: Signer 1 receives partial signatures, verifies them and creates a
     * partial signature to send B-coins to signer 0. */
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &musig_session_a[1], data_a, &partial_sig_a[0], &pk_a[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &musig_session_b[1], data_b, &partial_sig_b[0], &pk_b[0]) == 1);
    CHECK(secp256k1_musig_partial_sign(ctx, &musig_session_b[1], &partial_sig_b[1]));

    /* Step 5: Signer 0 adapts its own partial signature and combines it with the
     * partial signature from signer 1. This results in a complete signature which
     * is broadcasted by signer 0 to take B-coins. */
    CHECK(secp256k1_musig_partial_sig_adapt(ctx, &partial_sig_b_adapted[0], &partial_sig_b[0], sec_adaptor, combined_nonce_parity_b));
    memcpy(&partial_sig_b_adapted[1], &partial_sig_b[1], sizeof(partial_sig_b_adapted[1]));
    CHECK(secp256k1_musig_partial_sig_combine(ctx, &musig_session_b[0], final_sig_b, partial_sig_b_adapted, 2) == 1);
    CHECK(secp256k1_schnorrsig_verify(ctx, final_sig_b, msg32_b, sizeof(msg32_b), &combined_pk_b) == 1);

    /* Step 6: Signer 1 extracts adaptor from the published signature, applies it to
     * other partial signature, and takes A-coins. */
    CHECK(secp256k1_musig_extract_secret_adaptor(ctx, sec_adaptor_extracted, final_sig_b, partial_sig_b, 2, combined_nonce_parity_b) == 1);
    CHECK(memcmp(sec_adaptor_extracted, sec_adaptor, sizeof(sec_adaptor)) == 0); /* in real life we couldn't check this, of course */
    CHECK(secp256k1_musig_partial_sig_adapt(ctx, &partial_sig_a[0], &partial_sig_a[0], sec_adaptor_extracted, combined_nonce_parity_a));
    CHECK(secp256k1_musig_partial_sign(ctx, &musig_session_a[1], &partial_sig_a[1]));
    CHECK(secp256k1_musig_partial_sig_combine(ctx, &musig_session_a[1], final_sig_a, partial_sig_a, 2) == 1);
    CHECK(secp256k1_schnorrsig_verify(ctx, final_sig_a, msg32_a, sizeof(msg32_a), &combined_pk_a) == 1);
}

void sha256_tag_test_internal(secp256k1_sha256 *sha_tagged, unsigned char *tag, size_t taglen) {
    secp256k1_sha256 sha;
    unsigned char buf[32];
    unsigned char buf2[32];
    size_t i;

    secp256k1_sha256_initialize(&sha);
    secp256k1_sha256_write(&sha, tag, taglen);
    secp256k1_sha256_finalize(&sha, buf);
    /* buf = SHA256("KeyAgg coefficient") */

    secp256k1_sha256_initialize(&sha);
    secp256k1_sha256_write(&sha, buf, 32);
    secp256k1_sha256_write(&sha, buf, 32);
    /* Is buffer fully consumed? */
    CHECK((sha.bytes & 0x3F) == 0);

    /* Compare with tagged SHA */
    for (i = 0; i < 8; i++) {
        CHECK(sha_tagged->s[i] == sha.s[i]);
    }
    secp256k1_sha256_write(&sha, buf, 32);
    secp256k1_sha256_write(sha_tagged, buf, 32);
    secp256k1_sha256_finalize(&sha, buf);
    secp256k1_sha256_finalize(sha_tagged, buf2);
    CHECK(memcmp(buf, buf2, 32) == 0);
}

/* Checks that the initialized tagged hashes initialized have the expected
 * state. */
void sha256_tag_test(void) {
    secp256k1_sha256 sha_tagged;
    {
        char tag[11] = "KeyAgg list";
        secp256k1_musig_keyagglist_sha256(&sha_tagged);
        sha256_tag_test_internal(&sha_tagged, (unsigned char*)tag, sizeof(tag));
    }
    {
        char tag[18] = "KeyAgg coefficient";
        secp256k1_musig_keyaggcoef_sha256(&sha_tagged);
        sha256_tag_test_internal(&sha_tagged, (unsigned char*)tag, sizeof(tag));
    }
}

/* Attempts to create a signature for the combined public key using given secret
 * keys and pre_session. */
void musig_tweak_test_helper(const secp256k1_xonly_pubkey* combined_pubkey, const unsigned char *sk0, const unsigned char *sk1, secp256k1_musig_pre_session *pre_session) {
    secp256k1_musig_session session[2];
    secp256k1_musig_session_signer_data signers0[2];
    secp256k1_musig_session_signer_data signers1[2];
    secp256k1_xonly_pubkey pk[2];
    unsigned char session_id[2][32];
    unsigned char msg[32];
    unsigned char nonce_commitment[2][32];
    unsigned char nonce[2][32];
    const unsigned char *ncs[2];
    secp256k1_musig_partial_signature partial_sig[2];
    unsigned char final_sig[64];

    secp256k1_testrand256(session_id[0]);
    secp256k1_testrand256(session_id[1]);
    secp256k1_testrand256(msg);

    CHECK(secp256k1_xonly_pubkey_create(&pk[0], sk0) == 1);
    CHECK(secp256k1_xonly_pubkey_create(&pk[1], sk1) == 1);

    CHECK(secp256k1_musig_session_init(ctx, &session[0], signers0, nonce_commitment[0], session_id[0], msg, combined_pubkey, pre_session, 2, sk0) == 1);
    CHECK(secp256k1_musig_session_init(ctx, &session[1], signers1, nonce_commitment[1], session_id[1], msg, combined_pubkey, pre_session, 2, sk1) == 1);
    /* Set nonce commitments */
    ncs[0] = nonce_commitment[0];
    ncs[1] = nonce_commitment[1];
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session[0], signers0, nonce[0], ncs, 2, NULL) == 1);
    CHECK(secp256k1_musig_session_get_public_nonce(ctx, &session[1], signers1, nonce[1], ncs, 2, NULL) == 1);
    /* Set nonces */
    CHECK(secp256k1_musig_set_nonce(ctx, &signers0[0], nonce[0]) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers0[1], nonce[1]) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers1[0], nonce[0]) == 1);
    CHECK(secp256k1_musig_set_nonce(ctx, &signers1[1], nonce[1]) == 1);
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &session[0], signers0, 2, NULL, NULL) == 1);
    CHECK(secp256k1_musig_session_combine_nonces(ctx, &session[1], signers1, 2, NULL, NULL) == 1);
    CHECK(secp256k1_musig_partial_sign(ctx, &session[0], &partial_sig[0]) == 1);
    CHECK(secp256k1_musig_partial_sign(ctx, &session[1], &partial_sig[1]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[0], &signers0[1], &partial_sig[1], &pk[1]) == 1);
    CHECK(secp256k1_musig_partial_sig_verify(ctx, &session[1], &signers1[0], &partial_sig[0], &pk[0]) == 1);
    CHECK(secp256k1_musig_partial_sig_combine(ctx, &session[0], final_sig, partial_sig, 2));
    CHECK(secp256k1_schnorrsig_verify(ctx, final_sig, msg, sizeof(msg), combined_pubkey) == 1);
}

/* In this test we create a combined public key P and a commitment Q = P +
 * hash(P, contract)*G. Then we test that we can sign for both public keys. In
 * order to sign for Q we use the tweak32 argument of partial_sig_combine. */
void musig_tweak_test(secp256k1_scratch_space *scratch) {
    unsigned char sk[2][32];
    secp256k1_xonly_pubkey pk[2];
    const secp256k1_xonly_pubkey *pk_ptr[2];
    secp256k1_musig_pre_session pre_session_P;
    secp256k1_musig_pre_session pre_session_Q;
    secp256k1_xonly_pubkey P;
    unsigned char P_serialized[32];
    secp256k1_pubkey Q;
    int Q_parity;
    secp256k1_xonly_pubkey Q_xonly;
    unsigned char Q_serialized[32];

    secp256k1_sha256 sha;
    unsigned char contract[32];
    unsigned char ec_commit_tweak[32];

    /* Setup */
    secp256k1_testrand256(sk[0]);
    secp256k1_testrand256(sk[1]);
    secp256k1_testrand256(contract);

    pk_ptr[0] = &pk[0];
    pk_ptr[1] = &pk[1];
    CHECK(secp256k1_xonly_pubkey_create(&pk[0], sk[0]) == 1);
    CHECK(secp256k1_xonly_pubkey_create(&pk[1], sk[1]) == 1);
    CHECK(secp256k1_musig_pubkey_combine(ctx, scratch, &P, &pre_session_P, pk_ptr, 2) == 1);

    CHECK(secp256k1_xonly_pubkey_serialize(ctx, P_serialized, &P) == 1);
    secp256k1_sha256_initialize(&sha);
    secp256k1_sha256_write(&sha, P_serialized, 32);
    secp256k1_sha256_write(&sha, contract, 32);
    secp256k1_sha256_finalize(&sha, ec_commit_tweak);
    pre_session_Q = pre_session_P;
    CHECK(secp256k1_musig_pubkey_tweak_add(ctx, &pre_session_Q, &Q, &P, ec_commit_tweak) == 1);
    CHECK(secp256k1_xonly_pubkey_from_pubkey(ctx, &Q_xonly, &Q_parity, &Q));
    CHECK(secp256k1_xonly_pubkey_serialize(ctx, Q_serialized, &Q_xonly));
    /* Check that musig_pubkey_tweak_add produces same result as
     * xonly_pubkey_tweak_add. */
    CHECK(secp256k1_xonly_pubkey_tweak_add_check(ctx, Q_serialized, Q_parity, &P, ec_commit_tweak) == 1);

    /* Test signing for P */
    musig_tweak_test_helper(&P, sk[0], sk[1], &pre_session_P);
    /* Test signing for Q */
    musig_tweak_test_helper(&Q_xonly, sk[0], sk[1], &pre_session_Q);
}

void musig_test_vectors_helper(unsigned char pk_ser[][32], int n_pks, const unsigned char *combined_pk_expected, int has_second_pk, int second_pk_idx) {
    secp256k1_xonly_pubkey *pk = malloc(n_pks * sizeof(*pk));
    const secp256k1_xonly_pubkey **pk_ptr = malloc(n_pks * sizeof(*pk_ptr));
    secp256k1_xonly_pubkey combined_pk;
    unsigned char combined_pk_ser[32];
    secp256k1_musig_pre_session pre_session;
    secp256k1_fe second_pk_x;
    int i;

    for (i = 0; i < n_pks; i++) {
        CHECK(secp256k1_xonly_pubkey_parse(ctx, &pk[i], pk_ser[i]));
        pk_ptr[i] = &pk[i];
    }

    CHECK(secp256k1_musig_pubkey_combine(ctx, NULL, &combined_pk, &pre_session, pk_ptr, n_pks) == 1);
    CHECK(secp256k1_fe_set_b32(&second_pk_x, pre_session.second_pk));
    CHECK(secp256k1_fe_is_zero(&second_pk_x) == !has_second_pk);
    if (!secp256k1_fe_is_zero(&second_pk_x)) {
        CHECK(secp256k1_memcmp_var(&pk_ser[second_pk_idx], &pre_session.second_pk, sizeof(pk_ser[second_pk_idx])) == 0);
    }
    CHECK(secp256k1_xonly_pubkey_serialize(ctx, combined_pk_ser, &combined_pk));
    /* TODO: remove when test vectors are not expected to change anymore */
    /* int k, l; */
    /* printf("const unsigned char combined_pk_expected[32] = {\n"); */
    /* for (k = 0; k < 4; k++) { */
    /*     printf("    "); */
    /*     for (l = 0; l < 8; l++) { */
    /*         printf("0x%02X, ", combined_pk_ser[k*8+l]); */
    /*     } */
    /*     printf("\n"); */
    /* } */
    /* printf("};\n"); */
    CHECK(secp256k1_memcmp_var(combined_pk_ser, combined_pk_expected, sizeof(combined_pk_ser)) == 0);
    free(pk);
    free(pk_ptr);
}

void musig_test_vectors(void) {
    size_t i;
    unsigned char pk_ser_tmp[4][32];
    unsigned char pk_ser[3][32] = {
        /* X1 */
        {
            0xF9, 0x30, 0x8A, 0x01, 0x92, 0x58, 0xC3, 0x10,
            0x49, 0x34, 0x4F, 0x85, 0xF8, 0x9D, 0x52, 0x29,
            0xB5, 0x31, 0xC8, 0x45, 0x83, 0x6F, 0x99, 0xB0,
            0x86, 0x01, 0xF1, 0x13, 0xBC, 0xE0, 0x36, 0xF9
        },
        /* X2 */
        {
            0xDF, 0xF1, 0xD7, 0x7F, 0x2A, 0x67, 0x1C, 0x5F,
            0x36, 0x18, 0x37, 0x26, 0xDB, 0x23, 0x41, 0xBE,
            0x58, 0xFE, 0xAE, 0x1D, 0xA2, 0xDE, 0xCE, 0xD8,
            0x43, 0x24, 0x0F, 0x7B, 0x50, 0x2B, 0xA6, 0x59
         },
         /* X3 */
         {
            0x35, 0x90, 0xA9, 0x4E, 0x76, 0x8F, 0x8E, 0x18,
            0x15, 0xC2, 0xF2, 0x4B, 0x4D, 0x80, 0xA8, 0xE3,
            0x14, 0x93, 0x16, 0xC3, 0x51, 0x8C, 0xE7, 0xB7,
            0xAD, 0x33, 0x83, 0x68, 0xD0, 0x38, 0xCA, 0x66
         }
    };
    const unsigned char combined_pk_expected[4][32] = {
        { /* 0 */
            0xE5, 0x83, 0x01, 0x40, 0x51, 0x21, 0x95, 0xD7,
            0x4C, 0x83, 0x07, 0xE3, 0x96, 0x37, 0xCB, 0xE5,
            0xFB, 0x73, 0x0E, 0xBE, 0xAB, 0x80, 0xEC, 0x51,
            0x4C, 0xF8, 0x8A, 0x87, 0x7C, 0xEE, 0xEE, 0x0B,
        },
        { /* 1 */
            0xD7, 0x0C, 0xD6, 0x9A, 0x26, 0x47, 0xF7, 0x39,
            0x09, 0x73, 0xDF, 0x48, 0xCB, 0xFA, 0x2C, 0xCC,
            0x40, 0x7B, 0x8B, 0x2D, 0x60, 0xB0, 0x8C, 0x5F,
            0x16, 0x41, 0x18, 0x5C, 0x79, 0x98, 0xA2, 0x90,
        },
        { /* 2 */
            0x81, 0xA8, 0xB0, 0x93, 0x91, 0x2C, 0x9E, 0x48,
            0x14, 0x08, 0xD0, 0x97, 0x76, 0xCE, 0xFB, 0x48,
            0xAE, 0xB8, 0xB6, 0x54, 0x81, 0xB6, 0xBA, 0xAF,
            0xB3, 0xC5, 0x81, 0x01, 0x06, 0x71, 0x7B, 0xEB,
        },
        { /* 3 */
            0x2E, 0xB1, 0x88, 0x51, 0x88, 0x7E, 0x7B, 0xDC,
            0x5E, 0x83, 0x0E, 0x89, 0xB1, 0x9D, 0xDB, 0xC2,
            0x80, 0x78, 0xF1, 0xFA, 0x88, 0xAA, 0xD0, 0xAD,
            0x01, 0xCA, 0x06, 0xFE, 0x4F, 0x80, 0x21, 0x0B,
        },
    };

    for (i = 0; i < sizeof(combined_pk_expected)/sizeof(combined_pk_expected[0]); i++) {
        size_t n_pks;
        int has_second_pk;
        int second_pk_idx;
        switch (i) {
            case 0:
                /* [X1, X2, X3] */
                n_pks = 3;
                memcpy(pk_ser_tmp[0], pk_ser[0], sizeof(pk_ser_tmp[0]));
                memcpy(pk_ser_tmp[1], pk_ser[1], sizeof(pk_ser_tmp[1]));
                memcpy(pk_ser_tmp[2], pk_ser[2], sizeof(pk_ser_tmp[2]));
                has_second_pk = 1;
                second_pk_idx = 1;
                break;
            case 1:
                /* [X3, X2, X1] */
                n_pks = 3;
                memcpy(pk_ser_tmp[2], pk_ser[0], sizeof(pk_ser_tmp[0]));
                memcpy(pk_ser_tmp[1], pk_ser[1], sizeof(pk_ser_tmp[1]));
                memcpy(pk_ser_tmp[0], pk_ser[2], sizeof(pk_ser_tmp[2]));
                has_second_pk = 1;
                second_pk_idx = 1;
                break;
            case 2:
                /* [X1, X1, X1] */
                n_pks = 3;
                memcpy(pk_ser_tmp[0], pk_ser[0], sizeof(pk_ser_tmp[0]));
                memcpy(pk_ser_tmp[1], pk_ser[0], sizeof(pk_ser_tmp[1]));
                memcpy(pk_ser_tmp[2], pk_ser[0], sizeof(pk_ser_tmp[2]));
                has_second_pk = 0;
                second_pk_idx = 0; /* unchecked */
                break;
            case 3:
                /* [X1, X1, X2, X2] */
                n_pks = 4;
                memcpy(pk_ser_tmp[0], pk_ser[0], sizeof(pk_ser_tmp[0]));
                memcpy(pk_ser_tmp[1], pk_ser[0], sizeof(pk_ser_tmp[1]));
                memcpy(pk_ser_tmp[2], pk_ser[1], sizeof(pk_ser_tmp[2]));
                memcpy(pk_ser_tmp[3], pk_ser[1], sizeof(pk_ser_tmp[3]));
                has_second_pk = 1;
                second_pk_idx = 2; /* second_pk_idx = 3 is equally valid */
                break;
            default:
                CHECK(0);
        }
        musig_test_vectors_helper(pk_ser_tmp, n_pks, combined_pk_expected[i], has_second_pk, second_pk_idx);
    }
}

void run_musig_tests(void) {
    int i;
    secp256k1_scratch_space *scratch = secp256k1_scratch_space_create(ctx, 1024 * 1024);

    for (i = 0; i < count; i++) {
        musig_simple_test(scratch);
    }
    musig_api_tests(scratch);
    musig_state_machine_tests(scratch);
    for (i = 0; i < count; i++) {
        /* Run multiple times to ensure that pk and nonce have different y
         * parities */
        scriptless_atomic_swap(scratch);
        musig_tweak_test(scratch);
    }
    sha256_tag_test();
    musig_test_vectors();

    secp256k1_scratch_space_destroy(ctx, scratch);
}

#endif
