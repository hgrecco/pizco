
.. module:: pizco

Internals
=========

Agent
-----

The base of both :class:`Proxy` and :class:`Server` is the :class:`Agent`.
Each Agent has ZMQ sockets to communicate:

- a `REP` socket to receive requests. This is the main endpoint of the Agent.
- a `PUB` to emit notifications to other Agents.
- one `SUB` to subscribe to notifications from other Agents.
- one `REQ` per each Agent that it has to talk to (stored in self.connections)

The `REP` and `PUB` endpoint can be specified when the Agent is instantiated.
If no endpoint is given, the sockets will bind to a random tcp port.

Protocol
--------

Messages are multipart ZMQ messages. The conten

**FRAME 0:** Header (utf-8 encoded str)

Used for identification and filtering. It contains 3 string concatenated with a
`+` (plus sign).

1. The protocol version (currently PZC00).
2. A unique identifier for the sender.
3. A string specifying the topic of the message.

*example:* PZC00+urn:uuid:ad2d9eb0-c5f8-4bfb-a37d-6b7903b041f3+value_changed

**FRAME 1:** Serialization (utf-8 encoded str)

Indicates the serialization protocol used in FRAME 2. Current valid values are:

- 'pickle': use the highest version available of the pickle format (default).
- 'pickleN': use the N version of the pickle format.
- 'json': use json format.

**FRAME 2:** Content (binary blob)

The actual content of the message.

**FRAME 3:** Message ID (utf-8 encoded str)

A unique identifier for the message.

*example:* urn:uuid:b711f2b8-277d-40df-a283-6269331db251

**FRAME 4:** Signature (bytes)

HMAC sha1 signature of FRAME 0:4 concatenated with Agent.hmac_key


By default, Agents use an empty signature key (no signature) and
the `pickle` serializer. The simplest way to change these defaults is
by using the environmental variables `PZC_KEY` and `PZC_SER`.
You might want to change the serializer when running different agents
on different versions of Python as not all pickle versions are supported
in all python versions.

You can also change the protocol settings for an specific Agent by
passing a Protocol object when the Agent is created.


Proxy-Server Protocol
---------------------

Between the Proxy and the Server, the content of the message (Frame 2)
is a tuple of three elements, being the first utf-8 str defining the
subprotocol ('PSMessage'). The second and third elements specify the
action and the options for that action.
