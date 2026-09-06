angular
.module("Cleep")
.service("motioncontrolsService", ["rpcService", function(rpcService) {
    const self = this;

    self.updateSettings = function(settings) {
        return rpcService.sendCommand("update_settings", "motioncontrols", settings, 10.0);
    };

    self.getStatus = function() {
        return rpcService.sendCommand("get_status", "motioncontrols", {});
    };

    self.clearLastMotion = function() {
        return rpcService.sendCommand("clear_last_motion", "motioncontrols", {});
    };
}]);
