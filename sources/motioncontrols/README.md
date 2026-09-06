# Motion controls

Motion controls is a Cleep app module for detecting simple physical gestures on a Raspberry Pi device.

It is designed for an **LSM6DSOX accelerometer/gyroscope breakout connected over I2C**. The LSM6DSOX provides a 3-axis accelerometer and 3-axis gyroscope, which makes it suitable for both held rotations and short tap impulses.

## Detected gestures

- Right rotation
- Left rotation
- Front rotation
- Back rotation
- Right side tap
- Left side tap
- Top tap

Example mappings for a Toniebox-style player:

- Right rotation: fast forward
- Right side tap: next track
- Left side tap: previous track
- Top tap: pause or play

## Hardware

Use an LSM6DSOX breakout that exposes I2C and supports Raspberry Pi voltage levels.

Typical Raspberry Pi wiring:

- VIN or 3V: 3.3 V, or VIN if the breakout supports 3-5 V input
- GND: ground
- SDA: GPIO2, physical pin 3
- SCL: GPIO3, physical pin 5

Enable I2C on the Raspberry Pi before using the module.

The default I2C address is `0x6A`. Some breakouts can also use `0x6B`.

## Noise handling

Rotation detection uses low-pass filtered acceleration to estimate tilt from gravity. A rotation event is emitted only after the configured angle is held for a short time. Hysteresis and cooldowns prevent repeated events while the device remains tilted.

Tap detection uses the difference between raw acceleration and filtered gravity. It requires a strong, short impulse on a dominant axis, then applies cooldowns and ignores taps while the device is already tilted too far.

Tap reliability depends on sensor placement and the device enclosure. Mount the sensor firmly, then tune the tap threshold and axis ratio with the final case assembled.

## Events

`motioncontrols.rotation.detected`

Fields:

- `direction`: `right`, `left`, `front`, or `back`
- `axis`: sensor axis used for the decision
- `angle`: detected angle in degrees
- `threshold`: configured threshold in degrees
- `timestamp`: event timestamp

`motioncontrols.tap.detected`

Fields:

- `side`: `right`, `left`, or `top`
- `axis`: sensor axis used for the decision
- `acceleration_g`: detected impulse in g
- `confidence`: dominance ratio of the strongest axis
- `timestamp`: event timestamp

`motioncontrols.status.changed`

Fields:

- `enabled`
- `connected`
- `message`
- `timestamp`
