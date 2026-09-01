angular
.module("Cleep")
.service("mqttService", ["rpcService", function(rpcService) {
    const self = this;

    self.updateSettings = function(settings) {
        return rpcService.sendCommand("update_settings", "mqtt", settings, 10.0);
    };

    self.publish = function(topic, payload, qos, retain) {
        return rpcService.sendCommand("publish", "mqtt", {
            topic,
            payload,
            qos,
            retain,
        });
    };

    self.subscribe = function(topic, qos) {
        return rpcService.sendCommand("subscribe", "mqtt", {
            topic,
            qos,
        });
    };

    self.unsubscribe = function(topic) {
        return rpcService.sendCommand("unsubscribe", "mqtt", {
            topic,
        });
    };
}]);
