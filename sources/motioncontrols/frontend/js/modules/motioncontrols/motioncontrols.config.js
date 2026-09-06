angular
.module("Cleep")
.directive("motioncontrolsConfigComponent", ["toastService", "motioncontrolsService", "cleepService",
function(toast, motioncontrolsService, cleepService) {

    const motioncontrolsController = function() {
        const self = this;

        self.enabled = false;
        self.i2cAddressText = "0x6A";
        self.sampleRateHz = 100;
        self.rotationAngleDeg = 35;
        self.rotationHysteresisDeg = 8;
        self.rotationHoldMs = 250;
        self.rotationCooldownMs = 1000;
        self.tapThresholdG = 1.6;
        self.tapAxisRatio = 1.6;
        self.tapCooldownMs = 350;
        self.tapMaxTiltDeg = 20;
        self.tapMaxGyroDps = 450;
        self.gravityAlpha = 0.12;
        self.positiveXOptions = ["right", "left"];
        self.positiveXTapSide = "right";
        self.connected = false;
        self.readerRunning = false;
        self.lastError = null;
        self.lastMotion = null;

        self.$onInit = function() {
            cleepService.getModuleConfig("motioncontrols")
                .then(function(config) {
                    self.__loadFromConfig(config);
                });
        };

        self.__loadFromConfig = function(config) {
            self.enabled = config.enabled;
            self.i2cAddressText = "0x" + Number(config.i2c_address).toString(16).toUpperCase();
            self.sampleRateHz = config.sample_rate_hz;
            self.rotationAngleDeg = config.rotation_angle_deg;
            self.rotationHysteresisDeg = config.rotation_hysteresis_deg;
            self.rotationHoldMs = config.rotation_hold_ms;
            self.rotationCooldownMs = config.rotation_cooldown_ms;
            self.tapThresholdG = config.tap_threshold_g;
            self.tapAxisRatio = config.tap_axis_ratio;
            self.tapCooldownMs = config.tap_cooldown_ms;
            self.tapMaxTiltDeg = config.tap_max_tilt_deg;
            self.tapMaxGyroDps = config.tap_max_gyro_dps;
            self.gravityAlpha = config.gravity_alpha;
            self.positiveXTapSide = config.positive_x_tap_side;
            self.connected = config.connected;
            self.readerRunning = config.reader_running;
            self.lastError = config.last_error;
            self.lastMotion = config.last_motion;
        };

        self.__parseI2cAddress = function() {
            return parseInt(String(self.i2cAddressText).trim(), 0);
        };

        self.save = function() {
            motioncontrolsService.updateSettings({
                enabled: self.enabled,
                i2c_address: self.__parseI2cAddress(),
                sample_rate_hz: parseInt(self.sampleRateHz, 10),
                rotation_angle_deg: parseFloat(self.rotationAngleDeg),
                rotation_hysteresis_deg: parseFloat(self.rotationHysteresisDeg),
                rotation_hold_ms: parseInt(self.rotationHoldMs, 10),
                rotation_cooldown_ms: parseInt(self.rotationCooldownMs, 10),
                tap_threshold_g: parseFloat(self.tapThresholdG),
                tap_axis_ratio: parseFloat(self.tapAxisRatio),
                tap_cooldown_ms: parseInt(self.tapCooldownMs, 10),
                tap_max_tilt_deg: parseFloat(self.tapMaxTiltDeg),
                tap_max_gyro_dps: parseFloat(self.tapMaxGyroDps),
                gravity_alpha: parseFloat(self.gravityAlpha),
                positive_x_tap_side: self.positiveXTapSide,
            })
                .then(function(resp) {
                    return cleepService.reloadModuleConfig("motioncontrols");
                })
                .then(function(config) {
                    self.__loadFromConfig(config);
                    toast.success("Configuration saved.");
                });
        };

        self.refresh = function() {
            motioncontrolsService.getStatus()
                .then(function(status) {
                    self.connected = status.connected;
                    self.readerRunning = status.reader_running;
                    self.lastError = status.last_error;
                    self.lastMotion = status.last_motion;
                });
        };

        self.clearLastMotion = function() {
            motioncontrolsService.clearLastMotion()
                .then(function(resp) {
                    self.lastMotion = null;
                    toast.success("Last motion cleared.");
                });
        };
    };

    return {
        templateUrl: "motioncontrols.config.html",
        replace: true,
        scope: true,
        controller: motioncontrolsController,
        controllerAs: "$ctrl",
    };
}]);
