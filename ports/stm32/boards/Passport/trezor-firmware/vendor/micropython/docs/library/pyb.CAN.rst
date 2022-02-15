.. currentmodule:: pyb
.. _pyb.CAN:

class CAN -- controller area network communication bus
======================================================

CAN implements the standard CAN communications protocol.  At
the physical level it consists of 2 lines: RX and TX.  Note that
to connect the pyboard to a CAN bus you must use a CAN transceiver
to convert the CAN logic signals from the pyboard to the correct
voltage levels on the bus.

Example usage (works without anything connected)::

    from pyb import CAN
    can = CAN(1, CAN.LOOPBACK)
    can.setfilter(0, CAN.LIST16, 0, (123, 124, 125, 126))  # set a filter to receive messages with id=123, 124, 125 and 126
    can.send('message!', 123)   # send a message with id 123
    can.recv(0)                 # receive message on FIFO 0


Constructors
------------

.. class:: pyb.CAN(bus, ...)

   Construct a CAN object on the given bus.  *bus* can be 1-2, or ``'YA'`` or ``'YB'``.
   With no additional parameters, the CAN object is created but not
   initialised (it has the settings from the last initialisation of
   the bus, if any).  If extra arguments are given, the bus is initialised.
   See :meth:`CAN.init` for parameters of initialisation.

   The physical pins of the CAN buses are:

     - ``CAN(1)`` is on ``YA``: ``(RX, TX) = (Y3, Y4) = (PB8, PB9)``
     - ``CAN(2)`` is on ``YB``: ``(RX, TX) = (Y5, Y6) = (PB12, PB13)``

Class Methods
-------------
.. classmethod:: CAN.initfilterbanks(nr)

   Reset and disable all filter banks and assign how many banks should be available for CAN(1).

   STM32F405 has 28 filter banks that are shared between the two available CAN bus controllers.
   This function configures how many filter banks should be assigned to each. *nr* is the number of banks
   that will be assigned to CAN(1), the rest of the 28 are assigned to CAN(2).
   At boot, 14 banks are assigned to each controller.

Methods
-------

.. method:: CAN.init(mode, extframe=False, prescaler=100, *, sjw=1, bs1=6, bs2=8, auto_restart=False, baudrate=0, sample_point=75)

   Initialise the CAN bus with the given parameters:

     - *mode* is one of:  NORMAL, LOOPBACK, SILENT, SILENT_LOOPBACK
     - if *extframe* is True then the bus uses extended identifiers in the frames
       (29 bits); otherwise it uses standard 11 bit identifiers
     - *prescaler* is used to set the duration of 1 time quanta; the time quanta
       will be the input clock (PCLK1, see :meth:`pyb.freq()`) divided by the prescaler
     - *sjw* is the resynchronisation jump width in units of the time quanta;
       it can be 1, 2, 3, 4
     - *bs1* defines the location of the sample point in units of the time quanta;
       it can be between 1 and 1024 inclusive
     - *bs2* defines the location of the transmit point in units of the time quanta;
       it can be between 1 and 16 inclusive
     - *auto_restart* sets whether the controller will automatically try and restart
       communications after entering the bus-off state; if this is disabled then
       :meth:`~CAN.restart()` can be used to leave the bus-off state
     - *baudrate* if a baudrate other than 0 is provided, this function will try to automatically
       calculate a CAN bit-timing (overriding *prescaler*, *bs1* and *bs2*) that satisfies both
       the baudrate and the desired *sample_point*.
     - *sample_point* given in a percentage of the bit time, the *sample_point* specifies the position
       of the last bit sample with respect to the whole bit time. The default *sample_point* is 75%.

   The time quanta tq is the basic unit of time for the CAN bus.  tq is the CAN
   prescaler value divided by PCLK1 (the frequency of internal peripheral bus 1);
   see :meth:`pyb.freq()` to determine PCLK1.

   A single bit is made up of the synchronisation segment, which is always 1 tq.
   Then follows bit segment 1, then bit segment 2.  The sample point is after bit
   segment 1 finishes.  The transmit point is after bit segment 2 finishes.
   The baud rate will be 1/bittime, where the bittime is 1 + BS1 + BS2 multiplied
   by the time quanta tq.

   For example, with PCLK1=42MHz, prescaler=100, sjw=1, bs1=6, bs2=8, the value of
   tq is 2.38 microseconds.  The bittime is 35.7 microseconds, and the baudrate
   is 28kHz.

   See page 680 of the STM32F405 datasheet for more details.

.. method:: CAN.deinit()

   Turn off the CAN bus.

.. method:: CAN.restart()

   Force a software restart of the CAN controller without resetting its
   configuration.

   If the controller enters the bus-off state then it will no longer participate
   in bus activity.  If the controller is not configured to automatically restart
   (see :meth:`~CAN.init()`) then this method can be used to trigger a restart,
   and the controller will follow the CAN protocol to leave the bus-off state and
   go into the error active state.

.. method:: CAN.state()

   Return the state of the controller.  The return value can be one of:

   - ``CAN.STOPPED`` -- the controller is completely off and reset;
   - ``CAN.ERROR_ACTIVE`` -- the controller is on and in the Error Active state
     (both TEC and REC are less than 96);
   - ``CAN.ERROR_WARNING`` -- the controller is on and in the Error Warning state
     (at least one of TEC or REC is 96 or greater);
   - ``CAN.ERROR_PASSIVE`` -- the controller is on and in the Error Passive state
     (at least one of TEC or REC is 128 or greater);
   - ``CAN.BUS_OFF`` -- the controller is on but not participating in bus activity
     (TEC overflowed beyond 255).

.. method:: CAN.info([list])

   Get information about the controller's error states and TX and RX buffers.
   If *list* is provided then it should be a list object with at least 8 entries,
   which will be filled in with the information.  Otherwise a new list will be
   created and filled in.  In both cases the return value of the method is the
   populated list.

   The values in the list are:

   - TEC value
   - REC value
   - number of times the controller enterted the Error Warning state (wrapped
     around to 0 after 65535)
   - number of times the controller enterted the Error Passive state (wrapped
     around to 0 after 65535)
   - number of times the controller enterted the Bus Off state (wrapped
     around to 0 after 65535)
   - number of pending TX messages
   - number of pending RX messages on fifo 0
   - number of pending RX messages on fifo 1

.. method:: CAN.setfilter(bank, mode, fifo, params, *, rtr)

   Configure a filter bank:

   - *bank* is the filter bank that is to be configured.
   - *mode* is the mode the filter should operate in.
   - *fifo* is which fifo (0 or 1) a message should be stored in, if it is accepted by this filter.
   - *params* is an array of values the defines the filter. The contents of the array depends on the *mode* argument.

   +-----------+---------------------------------------------------------+
   |*mode*     |contents of *params* array                               |
   +===========+=========================================================+
   |CAN.LIST16 |Four 16 bit ids that will be accepted                    |
   +-----------+---------------------------------------------------------+
   |CAN.LIST32 |Two 32 bit ids that will be accepted                     |
   +-----------+---------------------------------------------------------+
   |CAN.MASK16 |Two 16 bit id/mask pairs. E.g. (1, 3, 4, 4)              |
   |           | | The first pair, 1 and 3 will accept all ids           |
   |           | | that have bit 0 = 1 and bit 1 = 0.                    |
   |           | | The second pair, 4 and 4, will accept all ids         |
   |           | | that have bit 2 = 1.                                  |
   +-----------+---------------------------------------------------------+
   |CAN.MASK32 |As with CAN.MASK16 but with only one 32 bit id/mask pair.|
   +-----------+---------------------------------------------------------+

   - *rtr* is an array of booleans that states if a filter should accept a
     remote transmission request message.  If this argument is not given
     then it defaults to ``False`` for all entries.  The length of the array
     depends on the *mode* argument.

   +-----------+----------------------+
   |*mode*     |length of *rtr* array |
   +===========+======================+
   |CAN.LIST16 |4                     |
   +-----------+----------------------+
   |CAN.LIST32 |2                     |
   +-----------+----------------------+
   |CAN.MASK16 |2                     |
   +-----------+----------------------+
   |CAN.MASK32 |1                     |
   +-----------+----------------------+

.. method:: CAN.clearfilter(bank)

   Clear and disables a filter bank:

   - *bank* is the filter bank that is to be cleared.

.. method:: CAN.any(fifo)

   Return ``True`` if any message waiting on the FIFO, else ``False``.

.. method:: CAN.recv(fifo, list=None, *, timeout=5000)

   Receive data on the bus:

     - *fifo* is an integer, which is the FIFO to receive on
     - *list* is an optional list object to be used as the return value
     - *timeout* is the timeout in milliseconds to wait for the receive.

   Return value: A tuple containing four values.

     - The id of the message.
     - A boolean that indicates if the message is an RTR message.
     - The FMI (Filter Match Index) value.
     - An array containing the data.

   If *list* is ``None`` then a new tuple will be allocated, as well as a new
   bytes object to contain the data (as the fourth element in the tuple).

   If *list* is not ``None`` then it should be a list object with a least four
   elements.  The fourth element should be a memoryview object which is created
   from either a bytearray or an array of type 'B' or 'b', and this array must
   have enough room for at least 8 bytes.  The list object will then be
   populated with the first three return values above, and the memoryview object
   will be resized inplace to the size of the data and filled in with that data.
   The same list and memoryview objects can be reused in subsequent calls to
   this method, providing a way of receiving data without using the heap.
   For example::

        buf = bytearray(8)
        lst = [0, 0, 0, memoryview(buf)]
        # No heap memory is allocated in the following call
        can.recv(0, lst)

.. method:: CAN.send(data, id, *, timeout=0, rtr=False)

   Send a message on the bus:

     - *data* is the data to send (an integer to send, or a buffer object).
     - *id* is the id of the message to be sent.
     - *timeout* is the timeout in milliseconds to wait for the send.
     - *rtr* is a boolean that specifies if the message shall be sent as
       a remote transmission request.  If *rtr* is True then only the length
       of *data* is used to fill in the DLC slot of the frame; the actual
       bytes in *data* are unused.

     If timeout is 0 the message is placed in a buffer in one of three hardware
     buffers and the method returns immediately. If all three buffers are in use
     an exception is thrown. If timeout is not 0, the method waits until the
     message is transmitted. If the message can't be transmitted within the
     specified time an exception is thrown.

   Return value: ``None``.

.. method:: CAN.rxcallback(fifo, fun)

   Register a function to be called when a message is accepted into a empty fifo:

   - *fifo* is the receiving fifo.
   - *fun* is the function to be called when the fifo becomes non empty.

   The callback function takes two arguments the first is the can object it self the second is
   a integer that indicates the reason for the callback.

   +--------+------------------------------------------------+
   | Reason |                                                |
   +========+================================================+
   | 0      | A message has been accepted into a empty FIFO. |
   +--------+------------------------------------------------+
   | 1      | The FIFO is full                               |
   +--------+------------------------------------------------+
   | 2      | A message has been lost due to a full FIFO     |
   +--------+------------------------------------------------+

   Example use of rxcallback::

     def cb0(bus, reason):
       print('cb0')
       if reason == 0:
           print('pending')
       if reason == 1:
           print('full')
       if reason == 2:
           print('overflow')

     can = CAN(1, CAN.LOOPBACK)
     can.rxcallback(0, cb0)

Constants
---------

.. data:: CAN.NORMAL
          CAN.LOOPBACK
          CAN.SILENT
          CAN.SILENT_LOOPBACK

   The mode of the CAN bus used in :meth:`~CAN.init()`.

.. data:: CAN.STOPPED
          CAN.ERROR_ACTIVE
          CAN.ERROR_WARNING
          CAN.ERROR_PASSIVE
          CAN.BUS_OFF

   Possible states of the CAN controller returned from :meth:`~CAN.state()`.

.. data:: CAN.LIST16
          CAN.MASK16
          CAN.LIST32
          CAN.MASK32

   The operation mode of a filter used in :meth:`~CAN.setfilter()`.
