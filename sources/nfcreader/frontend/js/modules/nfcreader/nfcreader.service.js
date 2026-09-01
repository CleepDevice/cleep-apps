angular
.module("Cleep")
.service("nfcreaderService", ["rpcService", function(rpcService) {
    const self = this;

    self.updateSettings = function(settings) {
        return rpcService.sendCommand("update_settings", "nfcreader", settings, 10.0);
    };

    self.getStatus = function() {
        return rpcService.sendCommand("get_status", "nfcreader", {});
    };

    self.clearLastTag = function() {
        return rpcService.sendCommand("clear_last_tag", "nfcreader", {});
    };
}]);
