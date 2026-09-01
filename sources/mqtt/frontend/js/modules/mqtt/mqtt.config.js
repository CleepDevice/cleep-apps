angular
.module("Cleep")
.directive("mqttConfigComponent", ["toastService", "mqttService", "cleepService",
function(toast, mqttService, cleepService) {

    const mqttController = function() {
        const self = this;

        self.enabled = false;
        self.host = "";
        self.port = 1883;
        self.clientId = "";
        self.username = "";
        self.password = "";
        self.tls = false;
        self.insecureTls = false;
        self.defaultQos = 0;
        self.retain = false;
        self.publishEvents = false;
        self.eventTopicPrefix = "";
        self.subscriptionsText = "";
        self.connected = false;
        self.lastError = null;
        self.testTopic = "cleep/test";
        self.testPayload = "{\"hello\":\"cleep\"}";

        self.$onInit = function() {
            cleepService.getModuleConfig("mqtt")
                .then(function(config) {
                    self.__loadFromConfig(config);
                });
        };

        self.__loadFromConfig = function(config) {
            self.enabled = config.enabled;
            self.host = config.host;
            self.port = config.port;
            self.clientId = config.client_id;
            self.username = config.username;
            self.password = "";
            self.tls = config.tls;
            self.insecureTls = config.insecure_tls;
            self.defaultQos = config.default_qos;
            self.retain = config.retain;
            self.publishEvents = config.publish_events;
            self.eventTopicPrefix = config.event_topic_prefix;
            self.connected = config.connected;
            self.lastError = config.last_error;
            self.subscriptionsText = (config.subscriptions || [])
                .map(function(subscription) {
                    return subscription.topic + " " + subscription.qos;
                })
                .join("\n");
        };

        self.__parseSubscriptions = function() {
            return self.subscriptionsText
                .split("\n")
                .map(function(line) {
                    return line.trim();
                })
                .filter(Boolean)
                .map(function(line) {
                    const parts = line.split(/\s+/);
                    return {
                        topic: parts[0],
                        qos: parts[1] ? parseInt(parts[1], 10) : self.defaultQos,
                    };
                });
        };

        self.save = function() {
            const settings = {
                enabled: self.enabled,
                host: self.host,
                port: parseInt(self.port, 10),
                client_id: self.clientId,
                username: self.username,
                tls: self.tls,
                insecure_tls: self.insecureTls,
                default_qos: parseInt(self.defaultQos, 10),
                retain: self.retain,
                subscriptions: self.__parseSubscriptions(),
                publish_events: self.publishEvents,
                event_topic_prefix: self.eventTopicPrefix,
            };

            if (self.password) {
                settings.password = self.password;
            }

            mqttService.updateSettings(settings)
                .then(function(resp) {
                    return cleepService.reloadModuleConfig("mqtt");
                })
                .then(function(config) {
                    self.__loadFromConfig(config);
                    toast.success("Configuration saved.");
                });
        };

        self.publishTest = function() {
            let payload = self.testPayload;
            try {
                payload = JSON.parse(self.testPayload);
            } catch (error) {
                payload = self.testPayload;
            }

            mqttService.publish(
                self.testTopic,
                payload,
                parseInt(self.defaultQos, 10),
                self.retain
            )
                .then(function(resp) {
                    toast.success("Message published.");
                });
        };
    };

    return {
        templateUrl: "mqtt.config.html",
        replace: true,
        scope: true,
        controller: mqttController,
        controllerAs: "$ctrl",
    };
}]);
