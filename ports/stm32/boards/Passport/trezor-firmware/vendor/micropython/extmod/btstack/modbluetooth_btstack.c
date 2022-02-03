/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2020 Damien P. George
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "py/runtime.h"
#include "py/mperrno.h"
#include "py/mphal.h"

#if MICROPY_PY_BLUETOOTH && MICROPY_BLUETOOTH_BTSTACK

#include "extmod/btstack/modbluetooth_btstack.h"
#include "extmod/modbluetooth.h"

#include "lib/btstack/src/btstack.h"

#define DEBUG_printf(...) // printf("btstack: " __VA_ARGS__)

#ifndef MICROPY_PY_BLUETOOTH_DEFAULT_GAP_NAME
#define MICROPY_PY_BLUETOOTH_DEFAULT_GAP_NAME "MPY BTSTACK"
#endif

// How long to wait for a controller to init/deinit.
// Some controllers can take up to 5-6 seconds in normal operation.
STATIC const uint32_t BTSTACK_INIT_DEINIT_TIMEOUT_MS = 15000;

// We need to know the attribute handle for the GAP device name (see GAP_DEVICE_NAME_UUID)
// so it can be put into the gatts_db before registering the services, and accessed
// efficiently when requesting an attribute in att_read_callback.  Because this is the
// first characteristic of the first service, it always has a handle value of 3.
STATIC const uint16_t BTSTACK_GAP_DEVICE_NAME_HANDLE = 3;

volatile int mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_OFF;

// sm_set_authentication_requirements is set-only, so cache current value.
#if MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING
STATIC uint8_t mp_bluetooth_btstack_sm_auth_req = 0;
#endif

#define ERRNO_BLUETOOTH_NOT_ACTIVE MP_ENODEV

STATIC int btstack_error_to_errno(int err) {
    DEBUG_printf("  --> btstack error: %d\n", err);
    if (err == ERROR_CODE_SUCCESS) {
        return 0;
    } else if (err == BTSTACK_ACL_BUFFERS_FULL || err == BTSTACK_MEMORY_ALLOC_FAILED) {
        return MP_ENOMEM;
    } else if (err == GATT_CLIENT_IN_WRONG_STATE) {
        return MP_EALREADY;
    } else if (err == GATT_CLIENT_BUSY) {
        return MP_EBUSY;
    } else if (err == GATT_CLIENT_NOT_CONNECTED) {
        return MP_ENOTCONN;
    } else {
        return MP_EINVAL;
    }
}

#if MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE
STATIC mp_obj_bluetooth_uuid_t create_mp_uuid(uint16_t uuid16, const uint8_t *uuid128) {
    mp_obj_bluetooth_uuid_t result;
    result.base.type = &mp_type_bluetooth_uuid;
    if (uuid16 != 0) {
        result.data[0] = uuid16 & 0xff;
        result.data[1] = (uuid16 >> 8) & 0xff;
        result.type = MP_BLUETOOTH_UUID_TYPE_16;
    } else {
        reverse_128(uuid128, result.data);
        result.type = MP_BLUETOOTH_UUID_TYPE_128;
    }
    return result;
}
#endif // MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE

// Notes on supporting background ops (e.g. an attempt to gatts_notify while
// an existing notification is in progress):

// GATTS Notify/Indicate (att_server_notify/indicate)
// * When available, copies buffer immediately.
// * Otherwise fails with BTSTACK_ACL_BUFFERS_FULL
// * Use att_server_request_to_send_notification/indication to get callback
//   * Takes btstack_context_callback_registration_t (and takes ownership) and conn_handle.
//   * Callback is invoked with just the context member of the btstack_context_callback_registration_t

// GATTC Write without response (gatt_client_write_value_of_characteristic_without_response)
// * When available, copies buffer immediately.
// * Otherwise, fails with GATT_CLIENT_BUSY.
// * Use gatt_client_request_can_write_without_response_event to get callback
//   * Takes btstack_packet_handler_t (function pointer) and conn_handle
//   * Callback is invoked, use gatt_event_can_write_without_response_get_handle to get the conn_handle (no other context)
//   * There can only be one pending gatt_client_request_can_write_without_response_event (otherwise we fail with EALREADY).

// GATTC Write with response (gatt_client_write_value_of_characteristic)
// * When peripheral is available, takes ownership of buffer.
// * Otherwise, fails with GATT_CLIENT_IN_WRONG_STATE (we fail the operation).
// * Raises GATT_EVENT_QUERY_COMPLETE to the supplied packet handler.

// For notify/indicate/write-without-response that proceed immediately, nothing extra required.
// For all other cases, buffer needs to be copied and protected from GC.
// For notify/indicate:
//  * btstack_context_callback_registration_t:
//     * needs to be malloc'ed
//     * needs to be protected from GC
//     * context arg needs to point back to the callback registration so it can be freed and un-protected
// For write-without-response
//  * only the conn_handle is available in the callback
//  * so we need a queue of conn_handle->(value_handle, copied buffer)

// Pending operation types.
enum {
    // Queued for sending when possible.
    MP_BLUETOOTH_BTSTACK_PENDING_NOTIFY, // Waiting for context callback
    MP_BLUETOOTH_BTSTACK_PENDING_INDICATE, // Waiting for context callback
    MP_BLUETOOTH_BTSTACK_PENDING_WRITE_NO_RESPONSE, // Waiting for conn handle
    // Hold buffer pointer until complete.
    MP_BLUETOOTH_BTSTACK_PENDING_WRITE, // Waiting for write done event
};

// Pending operation:
//  - Holds a GC reference to the copied outgoing buffer.
//  - Provides enough information for the callback handler to execute the desired operation.
struct _mp_btstack_pending_op_t {
    btstack_linked_item_t *next; // Must be first field to match btstack_linked_item.

    // See enum above.
    uint16_t op_type;

    // For all op types.
    uint16_t conn_handle;
    uint16_t value_handle;

    // For notify/indicate only.
    // context_registration.context will point back to this struct.
    btstack_context_callback_registration_t context_registration;

    // For notify/indicate/write-without-response, this is the actual buffer to send.
    // For write-with-response, just holding onto the buffer for GC ref.
    size_t len;
    uint8_t buf[];
};

// Must hold MICROPY_PY_BLUETOOTH_ENTER.
STATIC void btstack_remove_pending_operation(mp_btstack_pending_op_t *pending_op, bool del) {
    bool removed = btstack_linked_list_remove(&MP_STATE_PORT(bluetooth_btstack_root_pointers)->pending_ops, (btstack_linked_item_t *)pending_op);
    assert(removed);
    (void)removed;
    if (del) {
        m_del_var(mp_btstack_pending_op_t, uint8_t, pending_op->len, pending_op);
    }
}

// Called in response to a gatts_notify/indicate being unable to complete, which then calls
// att_server_request_to_send_notification.
// We now have an opportunity to re-try the operation with an empty ACL buffer.
STATIC void btstack_notify_indicate_ready_handler(void *context) {
    MICROPY_PY_BLUETOOTH_ENTER
    mp_btstack_pending_op_t *pending_op = (mp_btstack_pending_op_t *)context;
    DEBUG_printf("btstack_notify_indicate_ready_handler op_type=%d conn_handle=%d value_handle=%d len=%zu\n", pending_op->op_type, pending_op->conn_handle, pending_op->value_handle, pending_op->len);
    if (pending_op->op_type == MP_BLUETOOTH_BTSTACK_PENDING_NOTIFY) {
        int err = att_server_notify(pending_op->conn_handle, pending_op->value_handle, pending_op->buf, pending_op->len);
        DEBUG_printf("btstack_notify_indicate_ready_handler: sending notification err=%d\n", err);
        assert(err == ERROR_CODE_SUCCESS);
        (void)err;
    } else {
        assert(pending_op->op_type == MP_BLUETOOTH_BTSTACK_PENDING_INDICATE);
        int err = att_server_indicate(pending_op->conn_handle, pending_op->value_handle, NULL, 0);
        DEBUG_printf("btstack_notify_indicate_ready_handler: sending indication err=%d\n", err);
        assert(err == ERROR_CODE_SUCCESS);
        (void)err;
    }
    // Can't free the pending op as we're in IRQ context. Leave it for the GC.
    btstack_remove_pending_operation(pending_op, false /* del */);
    MICROPY_PY_BLUETOOTH_EXIT
}

// Register a pending background operation -- copies the buffer, and makes it known to the GC.
STATIC mp_btstack_pending_op_t *btstack_enqueue_pending_operation(uint16_t op_type, uint16_t conn_handle, uint16_t value_handle, const uint8_t *buf, size_t len) {
    DEBUG_printf("btstack_enqueue_pending_operation op_type=%d conn_handle=%d value_handle=%d len=%zu\n", op_type, conn_handle, value_handle, len);
    mp_btstack_pending_op_t *pending_op = m_new_obj_var(mp_btstack_pending_op_t, uint8_t, len);
    pending_op->op_type = op_type;
    pending_op->conn_handle = conn_handle;
    pending_op->value_handle = value_handle;
    pending_op->len = len;
    memcpy(pending_op->buf, buf, len);

    if (op_type == MP_BLUETOOTH_BTSTACK_PENDING_NOTIFY || op_type == MP_BLUETOOTH_BTSTACK_PENDING_INDICATE) {
        pending_op->context_registration.callback = &btstack_notify_indicate_ready_handler;
        pending_op->context_registration.context = pending_op;
    }

    MICROPY_PY_BLUETOOTH_ENTER
    bool added = btstack_linked_list_add(&MP_STATE_PORT(bluetooth_btstack_root_pointers)->pending_ops, (btstack_linked_item_t *)pending_op);
    assert(added);
    (void)added;
    MICROPY_PY_BLUETOOTH_EXIT

    return pending_op;
}

#if MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT

// Cleans up a pending op of the specified type for this conn_handle (and if specified, value_handle).
// Used by MP_BLUETOOTH_BTSTACK_PENDING_WRITE and MP_BLUETOOTH_BTSTACK_PENDING_WRITE_NO_RESPONSE.
// At the moment, both will set value_handle=0xffff as the events do not know their value_handle.
// TODO: Can we make btstack give us the value_handle for regular write (with response) so that we
// know for sure that we're using the correct entry.
STATIC mp_btstack_pending_op_t *btstack_finish_pending_operation(uint16_t op_type, uint16_t conn_handle, uint16_t value_handle, bool del) {
    MICROPY_PY_BLUETOOTH_ENTER
    DEBUG_printf("btstack_finish_pending_operation op_type=%d conn_handle=%d value_handle=%d\n", op_type, conn_handle, value_handle);
    btstack_linked_list_iterator_t it;
    btstack_linked_list_iterator_init(&it, &MP_STATE_PORT(bluetooth_btstack_root_pointers)->pending_ops);
    while (btstack_linked_list_iterator_has_next(&it)) {
        mp_btstack_pending_op_t *pending_op = (mp_btstack_pending_op_t *)btstack_linked_list_iterator_next(&it);

        if (pending_op->op_type == op_type && pending_op->conn_handle == conn_handle && (value_handle == 0xffff || pending_op->value_handle == value_handle)) {
            DEBUG_printf("btstack_finish_pending_operation: found value_handle=%d len=%zu\n", pending_op->value_handle, pending_op->len);
            btstack_remove_pending_operation(pending_op, del);
            MICROPY_PY_BLUETOOTH_EXIT
            return del ? NULL : pending_op;
        }
    }
    DEBUG_printf("btstack_finish_pending_operation: not found\n");
    MICROPY_PY_BLUETOOTH_EXIT
    return NULL;
}
#endif

// This needs to be separate to btstack_packet_handler otherwise we get
// dual-delivery of the HCI_EVENT_LE_META event.
STATIC void btstack_packet_handler_att_server(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    (void)channel;
    (void)size;
    DEBUG_printf("btstack_packet_handler_att_server(packet_type=%u, packet=%p)\n", packet_type, packet);
    if (packet_type != HCI_EVENT_PACKET) {
        return;
    }

    uint8_t event_type = hci_event_packet_get_type(packet);

    if (event_type == ATT_EVENT_CONNECTED) {
        DEBUG_printf("  --> att connected\n");
        // The ATT_EVENT_*CONNECTED events are fired for both peripheral and central role, with no way to tell which.
        // So we use the HCI_EVENT_LE_META event directly in the main packet handler.
    } else if (event_type == ATT_EVENT_DISCONNECTED) {
        DEBUG_printf("  --> att disconnected\n");
    } else if (event_type == ATT_EVENT_HANDLE_VALUE_INDICATION_COMPLETE) {
        DEBUG_printf("  --> att indication complete\n");
        uint16_t conn_handle = att_event_handle_value_indication_complete_get_conn_handle(packet);
        uint16_t value_handle = att_event_handle_value_indication_complete_get_attribute_handle(packet);
        uint8_t status = att_event_handle_value_indication_complete_get_status(packet);
        mp_bluetooth_gatts_on_indicate_complete(conn_handle, value_handle, status);
    } else if (event_type == ATT_EVENT_MTU_EXCHANGE_COMPLETE) {
        // This is triggered in peripheral mode, when exchange initiated by us or remote.
        uint16_t conn_handle = att_event_mtu_exchange_complete_get_handle(packet);
        uint16_t mtu = att_event_mtu_exchange_complete_get_MTU(packet);
        mp_bluetooth_gatts_on_mtu_exchanged(conn_handle, mtu);
    } else if (event_type == HCI_EVENT_LE_META || event_type == HCI_EVENT_DISCONNECTION_COMPLETE) {
        // Ignore, duplicated by att_server.c.
    } else {
        DEBUG_printf("  --> hci att server event type: unknown (0x%02x)\n", event_type);
    }
}

#if MICROPY_BLUETOOTH_USE_ZEPHYR_STATIC_ADDRESS
// During startup, the controller (e.g. Zephyr) might give us a static address that we can use.
STATIC uint8_t controller_static_addr[6] = {0};
STATIC bool controller_static_addr_available = false;

STATIC const uint8_t read_static_address_command_complete_prefix[] = { 0x0e, 0x1b, 0x01, 0x09, 0xfc };
#endif

STATIC void btstack_packet_handler(uint8_t packet_type, uint8_t *packet, uint8_t irq) {
    DEBUG_printf("btstack_packet_handler(packet_type=%u, packet=%p)\n", packet_type, packet);
    if (packet_type != HCI_EVENT_PACKET) {
        return;
    }

    uint8_t event_type = hci_event_packet_get_type(packet);

    if (event_type == HCI_EVENT_LE_META) {
        DEBUG_printf("  --> hci le meta\n");
        switch (hci_event_le_meta_get_subevent_code(packet)) {
            case HCI_SUBEVENT_LE_CONNECTION_COMPLETE: {
                uint16_t conn_handle = hci_subevent_le_connection_complete_get_connection_handle(packet);
                uint8_t addr_type = hci_subevent_le_connection_complete_get_peer_address_type(packet);
                bd_addr_t addr;
                hci_subevent_le_connection_complete_get_peer_address(packet, addr);
                uint16_t irq_event;
                if (hci_subevent_le_connection_complete_get_role(packet) == 0) {
                    // Master role.
                    irq_event = MP_BLUETOOTH_IRQ_PERIPHERAL_CONNECT;
                } else {
                    // Slave role.
                    irq_event = MP_BLUETOOTH_IRQ_CENTRAL_CONNECT;
                }
                mp_bluetooth_gap_on_connected_disconnected(irq_event, conn_handle, addr_type, addr);
                break;
            }
            case HCI_SUBEVENT_LE_CONNECTION_UPDATE_COMPLETE: {
                uint8_t status = hci_subevent_le_connection_update_complete_get_status(packet);
                uint16_t conn_handle = hci_subevent_le_connection_update_complete_get_connection_handle(packet);
                uint16_t conn_interval = hci_subevent_le_connection_update_complete_get_conn_interval(packet);
                uint16_t conn_latency = hci_subevent_le_connection_update_complete_get_conn_latency(packet);
                uint16_t supervision_timeout = hci_subevent_le_connection_update_complete_get_supervision_timeout(packet);
                DEBUG_printf("- LE Connection %04x: connection update - connection interval %u.%02u ms, latency %u, timeout %u\n",
                    conn_handle, conn_interval * 125 / 100, 25 * (conn_interval & 3), conn_latency, supervision_timeout);
                mp_bluetooth_gap_on_connection_update(conn_handle, conn_interval, conn_latency, supervision_timeout, status);
                break;
            }
        }
    } else if (event_type == BTSTACK_EVENT_STATE) {
        uint8_t state = btstack_event_state_get_state(packet);
        DEBUG_printf("  --> btstack event state 0x%02x\n", state);
        if (state == HCI_STATE_WORKING) {
            // Signal that initialisation has completed.
            mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_ACTIVE;
        } else if (state == HCI_STATE_HALTING) {
            // Signal that de-initialisation has begun.
            mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_HALTING;
        } else if (state == HCI_STATE_OFF) {
            // Signal that de-initialisation has completed.
            mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_OFF;
        }
    } else if (event_type == BTSTACK_EVENT_POWERON_FAILED) {
        // Signal that initialisation has failed.
        mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_OFF;
    } else if (event_type == HCI_EVENT_TRANSPORT_PACKET_SENT) {
        DEBUG_printf("  --> hci transport packet sent\n");
    } else if (event_type == HCI_EVENT_COMMAND_COMPLETE) {
        DEBUG_printf("  --> hci command complete\n");
        #if MICROPY_BLUETOOTH_USE_ZEPHYR_STATIC_ADDRESS
        if (memcmp(packet, read_static_address_command_complete_prefix, sizeof(read_static_address_command_complete_prefix)) == 0) {
            DEBUG_printf("  --> static address available\n");
            reverse_48(&packet[7], controller_static_addr);
            controller_static_addr_available = true;
        }
        #endif // MICROPY_BLUETOOTH_USE_ZEPHYR_STATIC_ADDRESS
    } else if (event_type == HCI_EVENT_COMMAND_STATUS) {
        DEBUG_printf("  --> hci command status\n");
    } else if (event_type == HCI_EVENT_NUMBER_OF_COMPLETED_PACKETS) {
        DEBUG_printf("  --> hci number of completed packets\n");
    } else if (event_type == BTSTACK_EVENT_NR_CONNECTIONS_CHANGED) {
        DEBUG_printf("  --> btstack # conns changed\n");
    } else if (event_type == HCI_EVENT_VENDOR_SPECIFIC) {
        DEBUG_printf("  --> hci vendor specific\n");
    } else if (event_type == SM_EVENT_AUTHORIZATION_RESULT ||
               event_type == SM_EVENT_PAIRING_COMPLETE ||
               // event_type == GAP_EVENT_DEDICATED_BONDING_COMPLETED || // No conn_handle
               event_type == HCI_EVENT_ENCRYPTION_CHANGE) {
        DEBUG_printf("  --> enc/auth/pair/bond change\n", );
        #if MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING
        uint16_t conn_handle;
        switch (event_type) {
            case SM_EVENT_AUTHORIZATION_RESULT:
                conn_handle = sm_event_authorization_result_get_handle(packet);
                break;
            case SM_EVENT_PAIRING_COMPLETE:
                conn_handle = sm_event_pairing_complete_get_handle(packet);
                break;
            case HCI_EVENT_ENCRYPTION_CHANGE:
                conn_handle = hci_event_encryption_change_get_connection_handle(packet);
                break;
            default:
                return;
        }

        hci_connection_t *hci_con = hci_connection_for_handle(conn_handle);
        sm_connection_t *desc = &hci_con->sm_connection;
        mp_bluetooth_gatts_on_encryption_update(conn_handle,
            desc->sm_connection_encrypted,
            desc->sm_connection_authenticated,
            desc->sm_le_db_index != -1,
            desc->sm_actual_encryption_key_size);
        #endif // MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING
    } else if (event_type == HCI_EVENT_DISCONNECTION_COMPLETE) {
        DEBUG_printf("  --> hci disconnect complete\n");
        uint16_t conn_handle = hci_event_disconnection_complete_get_connection_handle(packet);
        const hci_connection_t *conn = hci_connection_for_handle(conn_handle);
        uint16_t irq_event;
        if (conn == NULL || conn->role == 0) {
            // Master role.
            irq_event = MP_BLUETOOTH_IRQ_PERIPHERAL_DISCONNECT;
        } else {
            // Slave role.
            irq_event = MP_BLUETOOTH_IRQ_CENTRAL_DISCONNECT;
        }
        uint8_t addr[6] = {0};
        mp_bluetooth_gap_on_connected_disconnected(irq_event, conn_handle, 0xff, addr);
    #if MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE
    } else if (event_type == GAP_EVENT_ADVERTISING_REPORT) {
        DEBUG_printf("  --> gap advertising report\n");
        bd_addr_t address;
        gap_event_advertising_report_get_address(packet, address);
        uint8_t adv_event_type = gap_event_advertising_report_get_advertising_event_type(packet);
        uint8_t address_type = gap_event_advertising_report_get_address_type(packet);
        int8_t rssi = gap_event_advertising_report_get_rssi(packet);
        uint8_t length = gap_event_advertising_report_get_data_length(packet);
        const uint8_t *data = gap_event_advertising_report_get_data(packet);
        mp_bluetooth_gap_on_scan_result(address_type, address, adv_event_type, rssi, data, length);
    #endif // MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE
    #if MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT
    } else if (event_type == GATT_EVENT_QUERY_COMPLETE) {
        uint16_t conn_handle = gatt_event_query_complete_get_handle(packet);
        uint16_t status = gatt_event_query_complete_get_att_status(packet);
        DEBUG_printf("  --> gatt query complete irq=%d conn_handle=%d status=%d\n", irq, conn_handle, status);
        if (irq == MP_BLUETOOTH_IRQ_GATTC_READ_DONE || irq == MP_BLUETOOTH_IRQ_GATTC_WRITE_DONE) {
            // TODO there is no value_handle available to pass here.
            // TODO try and get this implemented in btstack.
            mp_bluetooth_gattc_on_read_write_status(irq, conn_handle, 0xffff, status);
            // Unref the saved buffer for the write operation on this conn_handle.
            if (irq == MP_BLUETOOTH_IRQ_GATTC_WRITE_DONE) {
                btstack_finish_pending_operation(MP_BLUETOOTH_BTSTACK_PENDING_WRITE, conn_handle, 0xffff, false /* del */);
            }
        } else if (irq == MP_BLUETOOTH_IRQ_GATTC_SERVICE_DONE ||
                   irq == MP_BLUETOOTH_IRQ_GATTC_CHARACTERISTIC_DONE ||
                   irq == MP_BLUETOOTH_IRQ_GATTC_DESCRIPTOR_DONE) {
            mp_bluetooth_gattc_on_discover_complete(irq, conn_handle, status);
        }
    } else if (event_type == GATT_EVENT_SERVICE_QUERY_RESULT) {
        DEBUG_printf("  --> gatt service query result\n");
        uint16_t conn_handle = gatt_event_service_query_result_get_handle(packet);
        gatt_client_service_t service;
        gatt_event_service_query_result_get_service(packet, &service);
        mp_obj_bluetooth_uuid_t service_uuid = create_mp_uuid(service.uuid16, service.uuid128);
        mp_bluetooth_gattc_on_primary_service_result(conn_handle, service.start_group_handle, service.end_group_handle, &service_uuid);
    } else if (event_type == GATT_EVENT_CHARACTERISTIC_QUERY_RESULT) {
        DEBUG_printf("  --> gatt characteristic query result\n");
        uint16_t conn_handle = gatt_event_characteristic_query_result_get_handle(packet);
        gatt_client_characteristic_t characteristic;
        gatt_event_characteristic_query_result_get_characteristic(packet, &characteristic);
        mp_obj_bluetooth_uuid_t characteristic_uuid = create_mp_uuid(characteristic.uuid16, characteristic.uuid128);
        mp_bluetooth_gattc_on_characteristic_result(conn_handle, characteristic.start_handle, characteristic.value_handle, characteristic.properties, &characteristic_uuid);
    } else if (event_type == GATT_EVENT_CHARACTERISTIC_DESCRIPTOR_QUERY_RESULT) {
        DEBUG_printf("  --> gatt descriptor query result\n");
        uint16_t conn_handle = gatt_event_all_characteristic_descriptors_query_result_get_handle(packet);
        gatt_client_characteristic_descriptor_t descriptor;
        gatt_event_all_characteristic_descriptors_query_result_get_characteristic_descriptor(packet, &descriptor);
        mp_obj_bluetooth_uuid_t descriptor_uuid = create_mp_uuid(descriptor.uuid16, descriptor.uuid128);
        mp_bluetooth_gattc_on_descriptor_result(conn_handle, descriptor.handle, &descriptor_uuid);
    } else if (event_type == GATT_EVENT_CHARACTERISTIC_VALUE_QUERY_RESULT) {
        DEBUG_printf("  --> gatt characteristic value query result\n");
        uint16_t conn_handle = gatt_event_characteristic_value_query_result_get_handle(packet);
        uint16_t value_handle = gatt_event_characteristic_value_query_result_get_value_handle(packet);
        uint16_t len = gatt_event_characteristic_value_query_result_get_value_length(packet);
        const uint8_t *data = gatt_event_characteristic_value_query_result_get_value(packet);
        mp_bluetooth_gattc_on_data_available(MP_BLUETOOTH_IRQ_GATTC_READ_RESULT, conn_handle, value_handle, &data, &len, 1);
    } else if (event_type == GATT_EVENT_NOTIFICATION) {
        DEBUG_printf("  --> gatt notification\n");
        uint16_t conn_handle = gatt_event_notification_get_handle(packet);
        uint16_t value_handle = gatt_event_notification_get_value_handle(packet);
        uint16_t len = gatt_event_notification_get_value_length(packet);
        const uint8_t *data = gatt_event_notification_get_value(packet);
        mp_bluetooth_gattc_on_data_available(MP_BLUETOOTH_IRQ_GATTC_NOTIFY, conn_handle, value_handle, &data, &len, 1);
    } else if (event_type == GATT_EVENT_INDICATION) {
        DEBUG_printf("  --> gatt indication\n");
        uint16_t conn_handle = gatt_event_indication_get_handle(packet);
        uint16_t value_handle = gatt_event_indication_get_value_handle(packet);
        uint16_t len = gatt_event_indication_get_value_length(packet);
        const uint8_t *data = gatt_event_indication_get_value(packet);
        mp_bluetooth_gattc_on_data_available(MP_BLUETOOTH_IRQ_GATTC_INDICATE, conn_handle, value_handle, &data, &len, 1);
    } else if (event_type == GATT_EVENT_CAN_WRITE_WITHOUT_RESPONSE) {
        uint16_t conn_handle = gatt_event_can_write_without_response_get_handle(packet);
        DEBUG_printf("  --> gatt can write without response %d\n", conn_handle);
        mp_btstack_pending_op_t *pending_op = btstack_finish_pending_operation(MP_BLUETOOTH_BTSTACK_PENDING_WRITE_NO_RESPONSE, conn_handle, 0xffff, false /* !del */);
        if (pending_op) {
            DEBUG_printf("  --> ready for value_handle=%d len=%zu\n", pending_op->value_handle, pending_op->len);
            gatt_client_write_value_of_characteristic_without_response(pending_op->conn_handle, pending_op->value_handle, pending_op->len, (uint8_t *)pending_op->buf);
            // Note: Can't "del" the pending_op from IRQ context. Leave it for the GC.
        }

    #endif // MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT
    } else {
        DEBUG_printf("  --> hci event type: unknown (0x%02x)\n", event_type);
    }
}

// Because the packet handler callbacks don't support an argument, we use a specific
// handler when we need to provide additional state to the handler (in the "irq" parameter).
// This is the generic handler for when you don't need extra state.
STATIC void btstack_packet_handler_generic(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    (void)channel;
    (void)size;
    btstack_packet_handler(packet_type, packet, 0);
}

STATIC btstack_packet_callback_registration_t hci_event_callback_registration = {
    .callback = &btstack_packet_handler_generic
};

#if MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT
// For when the handler is being used for service discovery.
STATIC void btstack_packet_handler_discover_services(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    (void)channel;
    (void)size;
    btstack_packet_handler(packet_type, packet, MP_BLUETOOTH_IRQ_GATTC_SERVICE_DONE);
}

// For when the handler is being used for characteristic discovery.
STATIC void btstack_packet_handler_discover_characteristics(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    (void)channel;
    (void)size;
    btstack_packet_handler(packet_type, packet, MP_BLUETOOTH_IRQ_GATTC_CHARACTERISTIC_DONE);
}

// For when the handler is being used for descriptor discovery.
STATIC void btstack_packet_handler_discover_descriptors(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    (void)channel;
    (void)size;
    btstack_packet_handler(packet_type, packet, MP_BLUETOOTH_IRQ_GATTC_DESCRIPTOR_DONE);
}

// For when the handler is being used for a read query.
STATIC void btstack_packet_handler_read(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    (void)channel;
    (void)size;
    btstack_packet_handler(packet_type, packet, MP_BLUETOOTH_IRQ_GATTC_READ_DONE);
}

// For when the handler is being used for write-with-response.
STATIC void btstack_packet_handler_write_with_response(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size) {
    (void)channel;
    (void)size;
    btstack_packet_handler(packet_type, packet, MP_BLUETOOTH_IRQ_GATTC_WRITE_DONE);
}
#endif // MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT

STATIC btstack_timer_source_t btstack_init_deinit_timeout;

STATIC void btstack_init_deinit_timeout_handler(btstack_timer_source_t *ds) {
    (void)ds;

    // Stop waiting for initialisation.
    // This signals both the loops in mp_bluetooth_init and mp_bluetooth_deinit,
    // as well as ports that run a polling loop.
    mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_TIMEOUT;
}

#if !MICROPY_BLUETOOTH_USE_MP_HAL_GET_MAC_STATIC_ADDRESS
STATIC void btstack_static_address_ready(void *arg) {
    DEBUG_printf("btstack_static_address_ready.\n");
    *(volatile bool *)arg = true;
}
#endif

STATIC bool set_public_address(void) {
    bd_addr_t local_addr;
    gap_local_bd_addr(local_addr);
    bd_addr_t null_addr = {0};
    if (memcmp(local_addr, null_addr, 6) == 0) {
        DEBUG_printf("set_public_address: No public address available.\n");
        return false;
    }
    DEBUG_printf("set_public_address: Using controller's public address.\n");
    gap_random_address_set_mode(GAP_RANDOM_ADDRESS_TYPE_OFF);
    return true;
}

STATIC void set_random_address(void) {
    #if MICROPY_BLUETOOTH_USE_ZEPHYR_STATIC_ADDRESS
    if (controller_static_addr_available) {
        DEBUG_printf("set_random_address: Using static address supplied by controller.\n");
        gap_random_address_set(controller_static_addr);
    } else
    #endif // MICROPY_BLUETOOTH_USE_ZEPHYR_STATIC_ADDRESS
    {
        bd_addr_t static_addr;

        #if MICROPY_BLUETOOTH_USE_MP_HAL_GET_MAC_STATIC_ADDRESS

        DEBUG_printf("set_random_address: Generating static address using mp_hal_get_mac\n");
        mp_hal_get_mac(MP_HAL_MAC_BDADDR, static_addr);
        // Mark it as STATIC (not RPA or NRPA).
        static_addr[0] |= 0xc0;

        #else

        DEBUG_printf("set_random_address: Generating random static address.\n");
        btstack_crypto_random_t sm_crypto_random_request;
        volatile bool ready = false;
        btstack_crypto_random_generate(&sm_crypto_random_request, static_addr, 6, &btstack_static_address_ready, (void *)&ready);
        while (!ready) {
            MICROPY_EVENT_POLL_HOOK
        }

        #endif // MICROPY_BLUETOOTH_USE_MP_HAL_GET_MAC_STATIC_ADDRESS

        DEBUG_printf("set_random_address: Address generated.\n");
        gap_random_address_set(static_addr);
    }

    // Wait for the controller to accept this address.
    while (true) {
        uint8_t addr_type;
        bd_addr_t addr;
        gap_le_get_own_address(&addr_type, addr);

        bd_addr_t null_addr = {0};
        if (memcmp(addr, null_addr, 6) != 0) {
            break;
        }

        MICROPY_EVENT_POLL_HOOK
    }
    DEBUG_printf("set_random_address: Address loaded by controller\n");
}

int mp_bluetooth_init(void) {
    DEBUG_printf("mp_bluetooth_init\n");

    if (mp_bluetooth_btstack_state == MP_BLUETOOTH_BTSTACK_STATE_ACTIVE) {
        return 0;
    }

    // Clean up if necessary.
    mp_bluetooth_deinit();

    btstack_memory_init();

    #if MICROPY_BLUETOOTH_USE_ZEPHYR_STATIC_ADDRESS
    controller_static_addr_available = false;
    #endif

    MP_STATE_PORT(bluetooth_btstack_root_pointers) = m_new0(mp_bluetooth_btstack_root_pointers_t, 1);
    mp_bluetooth_gatts_db_create(&MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db);

    // Set the default GAP device name.
    const char *gap_name = MICROPY_PY_BLUETOOTH_DEFAULT_GAP_NAME;
    size_t gap_len = strlen(gap_name);
    mp_bluetooth_gatts_db_create_entry(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, BTSTACK_GAP_DEVICE_NAME_HANDLE, gap_len);
    mp_bluetooth_gap_set_device_name((const uint8_t *)gap_name, gap_len);

    mp_bluetooth_btstack_port_init();
    mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_STARTING;

    l2cap_init();
    le_device_db_init();
    sm_init();

    // Set blank ER/IR keys to suppress BTstack warning.
    // TODO handle this correctly.
    sm_key_t dummy_key;
    memset(dummy_key, 0, sizeof(dummy_key));
    sm_set_er(dummy_key);
    sm_set_ir(dummy_key);

    #if MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT
    gatt_client_init();

    // We always require explicitly exchanging MTU with ble.gattc_exchange_mtu().
    gatt_client_mtu_enable_auto_negotiation(false);
    #endif // MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT

    // Register for HCI events.
    hci_add_event_handler(&hci_event_callback_registration);

    // Register for ATT server events.
    att_server_register_packet_handler(&btstack_packet_handler_att_server);

    // Set a timeout for HCI initialisation.
    btstack_run_loop_set_timer(&btstack_init_deinit_timeout, BTSTACK_INIT_DEINIT_TIMEOUT_MS);
    btstack_run_loop_set_timer_handler(&btstack_init_deinit_timeout, btstack_init_deinit_timeout_handler);
    btstack_run_loop_add_timer(&btstack_init_deinit_timeout);

    DEBUG_printf("mp_bluetooth_init: waiting for stack startup\n");

    // Either the HCI event will set state to ACTIVE, or the timeout will set it to TIMEOUT.
    mp_bluetooth_btstack_port_start();
    while (mp_bluetooth_btstack_state == MP_BLUETOOTH_BTSTACK_STATE_STARTING) {
        MICROPY_EVENT_POLL_HOOK
    }
    btstack_run_loop_remove_timer(&btstack_init_deinit_timeout);

    // Check for timeout.
    if (mp_bluetooth_btstack_state != MP_BLUETOOTH_BTSTACK_STATE_ACTIVE) {
        DEBUG_printf("mp_bluetooth_init: stack startup timed out\n");

        bool timeout = mp_bluetooth_btstack_state == MP_BLUETOOTH_BTSTACK_STATE_TIMEOUT;

        // Required to stop the polling loop.
        mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_OFF;
        // Attempt a shutdown (may not do anything).
        mp_bluetooth_btstack_port_deinit();

        // Clean up.
        MP_STATE_PORT(bluetooth_btstack_root_pointers) = NULL;

        return timeout ? MP_ETIMEDOUT : MP_EINVAL;
    }

    DEBUG_printf("mp_bluetooth_init: stack startup complete\n");

    // At this point if the controller has its own public address, btstack will know this.
    // However, if this is not available, then attempt to get a static address:
    //  - For a Zephyr controller on nRF, a static address will be available during startup.
    //  - Otherwise we ask the controller to generate a static address for us.
    // In either case, calling gap_random_address_set will set the mode to STATIC, and then
    // immediately set the address on the controller. We then wait until this address becomes available.

    if (!set_public_address()) {
        set_random_address();
    }

    #if MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT
    // Enable GATT_EVENT_NOTIFICATION/GATT_EVENT_INDICATION for all connections and handles.
    gatt_client_listen_for_characteristic_value_updates(&MP_STATE_PORT(bluetooth_btstack_root_pointers)->notification, &btstack_packet_handler_generic, GATT_CLIENT_ANY_CONNECTION, NULL);
    #endif // MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT

    return 0;
}

void mp_bluetooth_deinit(void) {
    DEBUG_printf("mp_bluetooth_deinit\n");

    // Nothing to do if not initialised.
    if (!MP_STATE_PORT(bluetooth_btstack_root_pointers)) {
        return;
    }

    mp_bluetooth_gap_advertise_stop();

    #if MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT
    // Remove our registration for notify/indicate.
    gatt_client_stop_listening_for_characteristic_value_updates(&MP_STATE_PORT(bluetooth_btstack_root_pointers)->notification);
    #endif // MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT

    // Set a timer that will forcibly set the state to TIMEOUT, which will stop the loop below.
    btstack_run_loop_set_timer(&btstack_init_deinit_timeout, BTSTACK_INIT_DEINIT_TIMEOUT_MS);
    btstack_run_loop_add_timer(&btstack_init_deinit_timeout);

    // This should result in a clean shutdown, which will set the state to OFF.
    // On Unix this is blocking (it joins on the poll thread), on other ports the loop below will wait unil
    // either timeout or clean shutdown.
    mp_bluetooth_btstack_port_deinit();
    while (mp_bluetooth_btstack_state == MP_BLUETOOTH_BTSTACK_STATE_ACTIVE) {
        MICROPY_EVENT_POLL_HOOK
    }
    btstack_run_loop_remove_timer(&btstack_init_deinit_timeout);

    mp_bluetooth_btstack_state = MP_BLUETOOTH_BTSTACK_STATE_OFF;
    MP_STATE_PORT(bluetooth_btstack_root_pointers) = NULL;

    DEBUG_printf("mp_bluetooth_deinit: complete\n");
}

bool mp_bluetooth_is_active(void) {
    return mp_bluetooth_btstack_state == MP_BLUETOOTH_BTSTACK_STATE_ACTIVE;
}

void mp_bluetooth_get_current_address(uint8_t *addr_type, uint8_t *addr) {
    if (!mp_bluetooth_is_active()) {
        mp_raise_OSError(ERRNO_BLUETOOTH_NOT_ACTIVE);
    }

    DEBUG_printf("mp_bluetooth_get_current_address\n");
    gap_le_get_own_address(addr_type, addr);
}

void mp_bluetooth_set_address_mode(uint8_t addr_mode) {
    if (!mp_bluetooth_is_active()) {
        mp_raise_OSError(ERRNO_BLUETOOTH_NOT_ACTIVE);
    }

    switch (addr_mode) {
        case MP_BLUETOOTH_ADDRESS_MODE_PUBLIC: {
            DEBUG_printf("mp_bluetooth_set_address_mode: public\n");
            if (!set_public_address()) {
                // No public address available.
                mp_raise_OSError(MP_EINVAL);
            }
            break;
        }
        case MP_BLUETOOTH_ADDRESS_MODE_RANDOM: {
            DEBUG_printf("mp_bluetooth_set_address_mode: random\n");
            set_random_address();
            break;
        }
        case MP_BLUETOOTH_ADDRESS_MODE_RPA:
        case MP_BLUETOOTH_ADDRESS_MODE_NRPA:
            // Not yet supported.
            mp_raise_OSError(MP_EINVAL);
    }
}

#if MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING
void mp_bluetooth_set_bonding(bool enabled) {
    if (enabled) {
        mp_bluetooth_btstack_sm_auth_req |= SM_AUTHREQ_BONDING;
    } else {
        mp_bluetooth_btstack_sm_auth_req &= ~SM_AUTHREQ_BONDING;
    }
    sm_set_authentication_requirements(mp_bluetooth_btstack_sm_auth_req);
}

void mp_bluetooth_set_mitm_protection(bool enabled) {
    if (enabled) {
        mp_bluetooth_btstack_sm_auth_req |= SM_AUTHREQ_MITM_PROTECTION;
    } else {
        mp_bluetooth_btstack_sm_auth_req &= ~SM_AUTHREQ_MITM_PROTECTION;
    }
    sm_set_authentication_requirements(mp_bluetooth_btstack_sm_auth_req);
}

void mp_bluetooth_set_le_secure(bool enabled) {
    if (enabled) {
        mp_bluetooth_btstack_sm_auth_req |= SM_AUTHREQ_SECURE_CONNECTION;
    } else {
        mp_bluetooth_btstack_sm_auth_req &= ~SM_AUTHREQ_SECURE_CONNECTION;
    }
    sm_set_authentication_requirements(mp_bluetooth_btstack_sm_auth_req);
}

void mp_bluetooth_set_io_capability(uint8_t capability) {
    sm_set_io_capabilities(capability);
}
#endif // MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING

size_t mp_bluetooth_gap_get_device_name(const uint8_t **buf) {
    uint8_t *value = NULL;
    size_t value_len = 0;
    mp_bluetooth_gatts_db_read(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, BTSTACK_GAP_DEVICE_NAME_HANDLE, &value, &value_len);
    *buf = value;
    return value_len;
}

int mp_bluetooth_gap_set_device_name(const uint8_t *buf, size_t len) {
    return mp_bluetooth_gatts_db_write(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, BTSTACK_GAP_DEVICE_NAME_HANDLE, buf, len);
}

int mp_bluetooth_gap_advertise_start(bool connectable, int32_t interval_us, const uint8_t *adv_data, size_t adv_data_len, const uint8_t *sr_data, size_t sr_data_len) {
    DEBUG_printf("mp_bluetooth_gap_advertise_start\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    uint16_t adv_int_min = interval_us / 625;
    uint16_t adv_int_max = interval_us / 625;
    uint8_t adv_type = connectable ? 0 : 2;
    bd_addr_t null_addr = {0};

    uint8_t direct_address_type = 0;
    uint8_t channel_map = 0x07; // Use all three broadcast channels.
    uint8_t filter_policy = 0x00; // None.

    gap_advertisements_set_params(adv_int_min, adv_int_max, adv_type, direct_address_type, null_addr, channel_map, filter_policy);

    // Copy the adv_data and sr_data into a persistent buffer (which is findable via the btstack root pointers).
    size_t total_bytes = adv_data_len + sr_data_len;
    if (total_bytes > MP_STATE_PORT(bluetooth_btstack_root_pointers)->adv_data_alloc) {
        // Resize if necessary.
        MP_STATE_PORT(bluetooth_btstack_root_pointers)->adv_data = m_new(uint8_t, total_bytes);
        MP_STATE_PORT(bluetooth_btstack_root_pointers)->adv_data_alloc = total_bytes;
    }
    uint8_t *data = MP_STATE_PORT(bluetooth_btstack_root_pointers)->adv_data;

    if (adv_data) {
        memcpy(data, (uint8_t *)adv_data, adv_data_len);
        gap_advertisements_set_data(adv_data_len, data);
        data += adv_data_len;
    }
    if (sr_data) {
        memcpy(data, (uint8_t *)sr_data, sr_data_len);
        gap_scan_response_set_data(sr_data_len, data);
    }

    gap_advertisements_enable(true);
    return 0;
}

void mp_bluetooth_gap_advertise_stop(void) {
    DEBUG_printf("mp_bluetooth_gap_advertise_stop\n");

    if (!mp_bluetooth_is_active()) {
        return;
    }

    gap_advertisements_enable(false);
    MP_STATE_PORT(bluetooth_btstack_root_pointers)->adv_data_alloc = 0;
    MP_STATE_PORT(bluetooth_btstack_root_pointers)->adv_data = NULL;
}

int mp_bluetooth_gatts_register_service_begin(bool append) {
    DEBUG_printf("mp_bluetooth_gatts_register_service_begin\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    if (!append) {
        // This will reset the DB.
        // Becase the DB is statically allocated, there's no problem with just re-initing it.
        // Note this would be a memory leak if we enabled HAVE_MALLOC (there's no API to free the existing db).
        att_db_util_init();

        att_db_util_add_service_uuid16(GAP_SERVICE_UUID);
        uint16_t handle = att_db_util_add_characteristic_uuid16(GAP_DEVICE_NAME_UUID, ATT_PROPERTY_READ | ATT_PROPERTY_DYNAMIC, ATT_SECURITY_NONE, ATT_SECURITY_NONE, NULL, 0);
        assert(handle == BTSTACK_GAP_DEVICE_NAME_HANDLE);
        (void)handle;

        att_db_util_add_service_uuid16(0x1801);
        att_db_util_add_characteristic_uuid16(0x2a05, ATT_PROPERTY_READ, ATT_SECURITY_NONE, ATT_SECURITY_NONE, NULL, 0);
    }

    return 0;
}

STATIC uint16_t att_read_callback(hci_con_handle_t connection_handle, uint16_t att_handle, uint16_t offset, uint8_t *buffer, uint16_t buffer_size) {
    // Should return data length, 0 for error, or -1 for delayed response.
    // For more details search "*att_read_callback*" in micropython/lib/btstack/doc/manual/docs/profiles.md
    (void)connection_handle;
    DEBUG_printf("att_read_callback (handle: %u, offset: %u, buffer: %p, size: %u)\n", att_handle, offset, buffer, buffer_size);
    mp_bluetooth_gatts_db_entry_t *entry = mp_bluetooth_gatts_db_lookup(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, att_handle);
    if (!entry) {
        DEBUG_printf("att_read_callback handle not found\n");
        return 0;
    }

    // Allow Python code to override value (by using gatts_write), or deny (by returning false) the read.
    // Note this will be a no-op if the ringbuffer implementation is being used, as the Python callback cannot
    // be executed synchronously. This is currently always the case for btstack.
    if ((buffer == NULL) && (buffer_size == 0)) {
        if (!mp_bluetooth_gatts_on_read_request(connection_handle, att_handle)) {
            DEBUG_printf("att_read_callback: read request denied\n");
            return 0;
        }
    }

    uint16_t ret = att_read_callback_handle_blob(entry->data, entry->data_len, offset, buffer, buffer_size);
    return ret;
}

STATIC int att_write_callback(hci_con_handle_t connection_handle, uint16_t att_handle, uint16_t transaction_mode, uint16_t offset, uint8_t *buffer, uint16_t buffer_size) {
    (void)offset;
    (void)transaction_mode;
    DEBUG_printf("att_write_callback (handle: %u, mode: %u, offset: %u, buffer: %p, size: %u)\n", att_handle, transaction_mode, offset, buffer, buffer_size);
    mp_bluetooth_gatts_db_entry_t *entry = mp_bluetooth_gatts_db_lookup(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, att_handle);
    if (!entry) {
        DEBUG_printf("att_write_callback handle not found\n");
        return 0; // TODO: Find status code for not-found.
    }

    // TODO: Use `offset` arg.
    size_t append_offset = 0;
    if (entry->append) {
        append_offset = entry->data_len;
    }
    entry->data_len = MIN(entry->data_alloc, buffer_size + append_offset);
    memcpy(entry->data + append_offset, buffer, entry->data_len - append_offset);

    mp_bluetooth_gatts_on_write(connection_handle, att_handle);

    return 0;
}

STATIC inline uint16_t get_uuid16(const mp_obj_bluetooth_uuid_t *uuid) {
    return (uuid->data[1] << 8) | uuid->data[0];
}

// Map MP_BLUETOOTH_CHARACTERISTIC_FLAG_ values to btstack read/write permission values.
STATIC void get_characteristic_permissions(uint16_t flags, uint16_t *read_permission, uint16_t *write_permission) {
    if (flags & MP_BLUETOOTH_CHARACTERISTIC_FLAG_READ_ENCRYPTED) {
        *read_permission = ATT_SECURITY_ENCRYPTED;
    } else if (flags & MP_BLUETOOTH_CHARACTERISTIC_FLAG_READ_AUTHENTICATED) {
        *read_permission = ATT_SECURITY_AUTHENTICATED;
    } else if (flags & MP_BLUETOOTH_CHARACTERISTIC_FLAG_READ_AUTHORIZED) {
        *read_permission = ATT_SECURITY_AUTHORIZED;
    } else {
        *read_permission = ATT_SECURITY_NONE;
    }

    if (flags & MP_BLUETOOTH_CHARACTERISTIC_FLAG_WRITE_ENCRYPTED) {
        *write_permission = ATT_SECURITY_ENCRYPTED;
    } else if (flags & MP_BLUETOOTH_CHARACTERISTIC_FLAG_WRITE_AUTHENTICATED) {
        *write_permission = ATT_SECURITY_AUTHENTICATED;
    } else if (flags & MP_BLUETOOTH_CHARACTERISTIC_FLAG_WRITE_AUTHORIZED) {
        *write_permission = ATT_SECURITY_AUTHORIZED;
    } else {
        *write_permission = ATT_SECURITY_NONE;
    }
}

int mp_bluetooth_gatts_register_service(mp_obj_bluetooth_uuid_t *service_uuid, mp_obj_bluetooth_uuid_t **characteristic_uuids, uint16_t *characteristic_flags, mp_obj_bluetooth_uuid_t **descriptor_uuids, uint16_t *descriptor_flags, uint8_t *num_descriptors, uint16_t *handles, size_t num_characteristics) {
    DEBUG_printf("mp_bluetooth_gatts_register_service\n");
    // Note: btstack expects BE UUIDs (which it immediately convertes to LE).
    // So we have to convert all our modbluetooth LE UUIDs to BE just for the att_db_util_add_* methods (using get_uuid16 above, and reverse_128 from btstackutil.h).

    // TODO: btstack's att_db_util_add_* methods have no bounds checking or validation.
    // Need some way to prevent additional services being added if we're out of space in the static buffer.

    if (service_uuid->type == MP_BLUETOOTH_UUID_TYPE_16) {
        att_db_util_add_service_uuid16(get_uuid16(service_uuid));
    } else if (service_uuid->type == MP_BLUETOOTH_UUID_TYPE_128) {
        uint8_t buffer[16];
        reverse_128(service_uuid->data, buffer);
        att_db_util_add_service_uuid128(buffer);
    } else {
        return MP_EINVAL;
    }

    size_t handle_index = 0;
    size_t descriptor_index = 0;
    static uint8_t cccb_buf[2] = {0};

    for (size_t i = 0; i < num_characteristics; ++i) {
        uint16_t props = (characteristic_flags[i] & 0x7f) | ATT_PROPERTY_DYNAMIC;
        uint16_t read_permission, write_permission;
        get_characteristic_permissions(characteristic_flags[i], &read_permission, &write_permission);
        if (characteristic_uuids[i]->type == MP_BLUETOOTH_UUID_TYPE_16) {
            handles[handle_index] = att_db_util_add_characteristic_uuid16(get_uuid16(characteristic_uuids[i]), props, read_permission, write_permission, NULL, 0);
        } else if (characteristic_uuids[i]->type == MP_BLUETOOTH_UUID_TYPE_128) {
            uint8_t buffer[16];
            reverse_128(characteristic_uuids[i]->data, buffer);
            handles[handle_index] = att_db_util_add_characteristic_uuid128(buffer, props, read_permission, write_permission, NULL, 0);
        } else {
            return MP_EINVAL;
        }
        mp_bluetooth_gatts_db_create_entry(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, handles[handle_index], MP_BLUETOOTH_DEFAULT_ATTR_LEN);
        // If a NOTIFY or INDICATE characteristic is added, then we need to manage a value for the CCCB.
        if (props & (ATT_PROPERTY_NOTIFY | ATT_PROPERTY_INDICATE)) {
            // btstack creates the CCCB as the next handle.
            mp_bluetooth_gatts_db_create_entry(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, handles[handle_index] + 1, MP_BLUETOOTH_CCCB_LEN);
            int ret = mp_bluetooth_gatts_db_write(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, handles[handle_index] + 1, cccb_buf, sizeof(cccb_buf));
            if (ret) {
                return ret;
            }
        }
        DEBUG_printf("mp_bluetooth_gatts_register_service: Registered char with handle %u\n", handles[handle_index]);
        ++handle_index;

        for (size_t j = 0; j < num_descriptors[i]; ++j) {
            props = (descriptor_flags[descriptor_index] & 0x7f) | ATT_PROPERTY_DYNAMIC;
            get_characteristic_permissions(descriptor_flags[descriptor_index], &read_permission, &write_permission);

            if (descriptor_uuids[descriptor_index]->type == MP_BLUETOOTH_UUID_TYPE_16) {
                handles[handle_index] = att_db_util_add_descriptor_uuid16(get_uuid16(descriptor_uuids[descriptor_index]), props, read_permission, write_permission, NULL, 0);
            } else if (descriptor_uuids[descriptor_index]->type == MP_BLUETOOTH_UUID_TYPE_128) {
                uint8_t buffer[16];
                reverse_128(descriptor_uuids[descriptor_index]->data, buffer);
                handles[handle_index] = att_db_util_add_descriptor_uuid128(buffer, props, read_permission, write_permission, NULL, 0);
            } else {
                return MP_EINVAL;
            }
            mp_bluetooth_gatts_db_create_entry(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, handles[handle_index], MP_BLUETOOTH_DEFAULT_ATTR_LEN);
            DEBUG_printf("mp_bluetooth_gatts_register_service: Registered desc with handle %u\n", handles[handle_index]);
            ++descriptor_index;
            ++handle_index;
        }
    }

    return 0;
}

int mp_bluetooth_gatts_register_service_end(void) {
    DEBUG_printf("mp_bluetooth_gatts_register_service_end\n");
    att_server_init(att_db_util_get_address(), &att_read_callback, &att_write_callback);
    return 0;
}

int mp_bluetooth_gatts_read(uint16_t value_handle, uint8_t **value, size_t *value_len) {
    DEBUG_printf("mp_bluetooth_gatts_read\n");
    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }
    return mp_bluetooth_gatts_db_read(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, value_handle, value, value_len);
}

int mp_bluetooth_gatts_write(uint16_t value_handle, const uint8_t *value, size_t value_len, bool send_update) {
    DEBUG_printf("mp_bluetooth_gatts_write\n");
    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }
    if (send_update) {
        return MP_EOPNOTSUPP;
    }
    return mp_bluetooth_gatts_db_write(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, value_handle, value, value_len);
}

int mp_bluetooth_gatts_notify(uint16_t conn_handle, uint16_t value_handle) {
    DEBUG_printf("mp_bluetooth_gatts_notify\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    // Note: btstack doesn't appear to support sending a notification without a value, so include the stored value.
    uint8_t *data = NULL;
    size_t len = 0;
    mp_bluetooth_gatts_db_read(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, value_handle, &data, &len);
    return mp_bluetooth_gatts_notify_send(conn_handle, value_handle, data, len);
}

int mp_bluetooth_gatts_notify_send(uint16_t conn_handle, uint16_t value_handle, const uint8_t *value, size_t value_len) {
    DEBUG_printf("mp_bluetooth_gatts_notify_send\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    // Attempt to send immediately. If it succeeds, btstack will copy the buffer.
    MICROPY_PY_BLUETOOTH_ENTER
    int err = att_server_notify(conn_handle, value_handle, value, value_len);
    MICROPY_PY_BLUETOOTH_EXIT

    if (err == BTSTACK_ACL_BUFFERS_FULL) {
        DEBUG_printf("mp_bluetooth_gatts_notify_send: ACL buffer full, scheduling callback\n");
        // Schedule callback, making a copy of the buffer.
        mp_btstack_pending_op_t *pending_op = btstack_enqueue_pending_operation(MP_BLUETOOTH_BTSTACK_PENDING_NOTIFY, conn_handle, value_handle, value, value_len);

        err = att_server_request_to_send_notification(&pending_op->context_registration, conn_handle);

        if (err != ERROR_CODE_SUCCESS) {
            // Failure. Unref and free the pending operation.
            btstack_remove_pending_operation(pending_op, true /* del */);
        }

        return 0;
    } else {
        return btstack_error_to_errno(err);
    }
}

int mp_bluetooth_gatts_indicate(uint16_t conn_handle, uint16_t value_handle) {
    DEBUG_printf("mp_bluetooth_gatts_indicate\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    uint8_t *data = NULL;
    size_t len = 0;
    mp_bluetooth_gatts_db_read(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, value_handle, &data, &len);

    // Indicate will raise ATT_EVENT_HANDLE_VALUE_INDICATION_COMPLETE when
    // acknowledged (or timeout/error).

    // Attempt to send immediately, will copy buffer.
    MICROPY_PY_BLUETOOTH_ENTER
    int err = att_server_indicate(conn_handle, value_handle, data, len);
    MICROPY_PY_BLUETOOTH_EXIT

    if (err == BTSTACK_ACL_BUFFERS_FULL) {
        DEBUG_printf("mp_bluetooth_gatts_indicate: ACL buffer full, scheduling callback\n");
        // Schedule callback, making a copy of the buffer.
        mp_btstack_pending_op_t *pending_op = btstack_enqueue_pending_operation(MP_BLUETOOTH_BTSTACK_PENDING_INDICATE, conn_handle, value_handle, data, len);

        err = att_server_request_to_send_indication(&pending_op->context_registration, conn_handle);

        if (err != ERROR_CODE_SUCCESS) {
            // Failure. Unref and free the pending operation.
            btstack_remove_pending_operation(pending_op, true /* del */);
        }

        return 0;
    } else {
        return btstack_error_to_errno(err);
    }
}

int mp_bluetooth_gatts_set_buffer(uint16_t value_handle, size_t len, bool append) {
    DEBUG_printf("mp_bluetooth_gatts_set_buffer\n");
    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }
    return mp_bluetooth_gatts_db_resize(MP_STATE_PORT(bluetooth_btstack_root_pointers)->gatts_db, value_handle, len, append);
}

int mp_bluetooth_get_preferred_mtu(void) {
    if (!mp_bluetooth_is_active()) {
        mp_raise_OSError(ERRNO_BLUETOOTH_NOT_ACTIVE);
    }
    return l2cap_max_le_mtu();
}

int mp_bluetooth_set_preferred_mtu(uint16_t mtu) {
    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }
    l2cap_set_max_le_mtu(mtu);
    if (l2cap_max_le_mtu() != mtu) {
        return MP_EINVAL;
    }
    return 0;
}

int mp_bluetooth_gap_disconnect(uint16_t conn_handle) {
    DEBUG_printf("mp_bluetooth_gap_disconnect\n");
    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }
    gap_disconnect(conn_handle);
    return 0;
}

#if MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING

int mp_bluetooth_gap_pair(uint16_t conn_handle) {
    DEBUG_printf("mp_bluetooth_gap_pair: conn_handle=%d\n", conn_handle);
    sm_request_pairing(conn_handle);
    return 0;
}

int mp_bluetooth_gap_passkey(uint16_t conn_handle, uint8_t action, mp_int_t passkey) {
    DEBUG_printf("mp_bluetooth_gap_passkey: conn_handle=%d action=%d passkey=%d\n", conn_handle, action, (int)passkey);
    return MP_EOPNOTSUPP;
}

#endif // MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING

#if MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE
STATIC btstack_timer_source_t scan_duration_timeout;

STATIC void scan_duration_timeout_handler(btstack_timer_source_t *ds) {
    (void)ds;
    mp_bluetooth_gap_scan_stop();
}

int mp_bluetooth_gap_scan_start(int32_t duration_ms, int32_t interval_us, int32_t window_us, bool active_scan) {
    DEBUG_printf("mp_bluetooth_gap_scan_start\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    if (duration_ms > 0) {
        btstack_run_loop_set_timer(&scan_duration_timeout, duration_ms);
        btstack_run_loop_set_timer_handler(&scan_duration_timeout, scan_duration_timeout_handler);
        btstack_run_loop_add_timer(&scan_duration_timeout);
    }

    gap_set_scan_parameters(active_scan ? 1 : 0, interval_us / 625, window_us / 625);
    gap_start_scan();

    return 0;
}

int mp_bluetooth_gap_scan_stop(void) {
    DEBUG_printf("mp_bluetooth_gap_scan_stop\n");
    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }
    btstack_run_loop_remove_timer(&scan_duration_timeout);
    gap_stop_scan();
    mp_bluetooth_gap_on_scan_complete();
    return 0;
}

int mp_bluetooth_gap_peripheral_connect(uint8_t addr_type, const uint8_t *addr, int32_t duration_ms) {
    DEBUG_printf("mp_bluetooth_gap_peripheral_connect\n");

    uint16_t conn_scan_interval = 60000 / 625;
    uint16_t conn_scan_window = 30000 / 625;
    uint16_t conn_interval_min = 10000 / 1250;
    uint16_t conn_interval_max = 30000 / 1250;
    uint16_t conn_latency = 4;
    uint16_t supervision_timeout = duration_ms / 10; // default = 720
    uint16_t min_ce_length = 10000 / 625;
    uint16_t max_ce_length = 30000 / 625;

    gap_set_connection_parameters(conn_scan_interval, conn_scan_window, conn_interval_min, conn_interval_max, conn_latency, supervision_timeout, min_ce_length, max_ce_length);

    bd_addr_t btstack_addr;
    memcpy(btstack_addr, addr, BD_ADDR_LEN);
    return btstack_error_to_errno(gap_connect(btstack_addr, addr_type));
}

#endif // MICROPY_PY_BLUETOOTH_ENABLE_CENTRAL_MODE

#if MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT

int mp_bluetooth_gattc_discover_primary_services(uint16_t conn_handle, const mp_obj_bluetooth_uuid_t *uuid) {
    DEBUG_printf("mp_bluetooth_gattc_discover_primary_services\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    uint8_t err;
    if (uuid) {
        if (uuid->type == MP_BLUETOOTH_UUID_TYPE_16) {
            err = gatt_client_discover_primary_services_by_uuid16(&btstack_packet_handler_discover_services, conn_handle, get_uuid16(uuid));
        } else if (uuid->type == MP_BLUETOOTH_UUID_TYPE_128) {
            uint8_t buffer[16];
            reverse_128(uuid->data, buffer);
            err = gatt_client_discover_primary_services_by_uuid128(&btstack_packet_handler_discover_services, conn_handle, buffer);
        } else {
            DEBUG_printf("  --> unknown UUID size\n");
            return MP_EINVAL;
        }
    } else {
        err = gatt_client_discover_primary_services(&btstack_packet_handler_discover_services, conn_handle);
    }
    return btstack_error_to_errno(err);
}

int mp_bluetooth_gattc_discover_characteristics(uint16_t conn_handle, uint16_t start_handle, uint16_t end_handle, const mp_obj_bluetooth_uuid_t *uuid) {
    DEBUG_printf("mp_bluetooth_gattc_discover_characteristics\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    gatt_client_service_t service = {
        // Only start/end handles needed for gatt_client_discover_characteristics_for_service.
        .start_group_handle = start_handle,
        .end_group_handle = end_handle,
        .uuid16 = 0,
        .uuid128 = {0},
    };
    uint8_t err;
    if (uuid) {
        if (uuid->type == MP_BLUETOOTH_UUID_TYPE_16) {
            err = gatt_client_discover_characteristics_for_service_by_uuid16(&btstack_packet_handler_discover_characteristics, conn_handle, &service, get_uuid16(uuid));
        } else if (uuid->type == MP_BLUETOOTH_UUID_TYPE_128) {
            uint8_t buffer[16];
            reverse_128(uuid->data, buffer);
            err = gatt_client_discover_characteristics_for_service_by_uuid128(&btstack_packet_handler_discover_characteristics, conn_handle, &service, buffer);
        } else {
            DEBUG_printf("  --> unknown UUID size\n");
            return MP_EINVAL;
        }
    } else {
        err = gatt_client_discover_characteristics_for_service(&btstack_packet_handler_discover_characteristics, conn_handle, &service);
    }
    return btstack_error_to_errno(err);
}

int mp_bluetooth_gattc_discover_descriptors(uint16_t conn_handle, uint16_t start_handle, uint16_t end_handle) {
    DEBUG_printf("mp_bluetooth_gattc_discover_descriptors\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    gatt_client_characteristic_t characteristic = {
        // Only start/end handles needed for gatt_client_discover_characteristic_descriptors.
        .start_handle = start_handle,
        .value_handle = 0,
        .end_handle = end_handle,
        .properties = 0,
        .uuid16 = 0,
        .uuid128 = {0},
    };
    return btstack_error_to_errno(gatt_client_discover_characteristic_descriptors(&btstack_packet_handler_discover_descriptors, conn_handle, &characteristic));
}

int mp_bluetooth_gattc_read(uint16_t conn_handle, uint16_t value_handle) {
    DEBUG_printf("mp_bluetooth_gattc_read\n");
    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }
    return btstack_error_to_errno(gatt_client_read_value_of_characteristic_using_value_handle(&btstack_packet_handler_read, conn_handle, value_handle));
}

int mp_bluetooth_gattc_write(uint16_t conn_handle, uint16_t value_handle, const uint8_t *value, size_t *value_len, unsigned int mode) {
    DEBUG_printf("mp_bluetooth_gattc_write\n");

    if (!mp_bluetooth_is_active()) {
        return ERRNO_BLUETOOTH_NOT_ACTIVE;
    }

    // We should be distinguishing between gatt_client_write_value_of_characteristic vs
    // gatt_client_write_characteristic_descriptor_using_descriptor_handle.
    // However both are implemented using send_gatt_write_attribute_value_request under the hood,
    // and we get the exact same event to the packet handler.
    // Same story for the "without response" version.

    int err;
    mp_btstack_pending_op_t *pending_op = NULL;

    if (mode == MP_BLUETOOTH_WRITE_MODE_NO_RESPONSE) {
        // If possible, this will send immediately, copying the buffer directly to the ACL buffer.
        err = gatt_client_write_value_of_characteristic_without_response(conn_handle, value_handle, *value_len, (uint8_t *)value);
        if (err == GATT_CLIENT_BUSY) {
            DEBUG_printf("mp_bluetooth_gattc_write: client busy\n");
            // Can't send right now, need to take a copy of the buffer and add it to the queue.
            pending_op = btstack_enqueue_pending_operation(MP_BLUETOOTH_BTSTACK_PENDING_WRITE_NO_RESPONSE, conn_handle, value_handle, value, *value_len);
            // Notify when this conn_handle can write.
            err = gatt_client_request_can_write_without_response_event(&btstack_packet_handler_generic, conn_handle);
        } else {
            DEBUG_printf("mp_bluetooth_gattc_write: other failure: %d\n", err);
        }
    } else if (mode == MP_BLUETOOTH_WRITE_MODE_WITH_RESPONSE) {
        // Pending operation copies the value buffer and keeps a GC reference
        // until the response comes back (there is always a response).
        pending_op = btstack_enqueue_pending_operation(MP_BLUETOOTH_BTSTACK_PENDING_WRITE, conn_handle, value_handle, value, *value_len);
        err = gatt_client_write_value_of_characteristic(&btstack_packet_handler_write_with_response, conn_handle, value_handle, pending_op->len, pending_op->buf);
    } else {
        return MP_EINVAL;
    }

    if (pending_op && err != ERROR_CODE_SUCCESS) {
        // Failure. Unref and free the pending operation.
        btstack_remove_pending_operation(pending_op, true /* del */);
    }

    return btstack_error_to_errno(err);
}

int mp_bluetooth_gattc_exchange_mtu(uint16_t conn_handle) {
    DEBUG_printf("mp_bluetooth_exchange_mtu: conn_handle=%d mtu=%d\n", conn_handle, l2cap_max_le_mtu());

    gatt_client_send_mtu_negotiation(&btstack_packet_handler_att_server, conn_handle);

    return 0;
}
#endif // MICROPY_PY_BLUETOOTH_ENABLE_GATT_CLIENT

#if MICROPY_PY_BLUETOOTH_ENABLE_L2CAP_CHANNELS

int mp_bluetooth_l2cap_listen(uint16_t psm, uint16_t mtu) {
    DEBUG_printf("mp_bluetooth_l2cap_listen: psm=%d, mtu=%d\n", psm, mtu);
    return MP_EOPNOTSUPP;
}

int mp_bluetooth_l2cap_connect(uint16_t conn_handle, uint16_t psm, uint16_t mtu) {
    DEBUG_printf("mp_bluetooth_l2cap_connect: conn_handle=%d, psm=%d, mtu=%d\n", conn_handle, psm, mtu);
    return MP_EOPNOTSUPP;
}

int mp_bluetooth_l2cap_disconnect(uint16_t conn_handle, uint16_t cid) {
    DEBUG_printf("mp_bluetooth_l2cap_disconnect: conn_handle=%d, cid=%d\n", conn_handle, cid);
    return MP_EOPNOTSUPP;
}

int mp_bluetooth_l2cap_send(uint16_t conn_handle, uint16_t cid, const uint8_t *buf, size_t len, bool *stalled) {
    DEBUG_printf("mp_bluetooth_l2cap_send: conn_handle=%d, cid=%d, len=%d\n", conn_handle, cid, (int)len);
    return MP_EOPNOTSUPP;
}

int mp_bluetooth_l2cap_recvinto(uint16_t conn_handle, uint16_t cid, uint8_t *buf, size_t *len) {
    DEBUG_printf("mp_bluetooth_l2cap_recvinto: conn_handle=%d, cid=%d, len=%d\n", conn_handle, cid, (int)*len);
    return MP_EOPNOTSUPP;
}

#endif // MICROPY_PY_BLUETOOTH_ENABLE_L2CAP_CHANNELS

#endif // MICROPY_PY_BLUETOOTH && MICROPY_BLUETOOTH_BTSTACK
