angular
.module("Cleep")
.directive("nfcreaderConfigComponent", ["toastService", "nfcreaderService", "cleepService",
function(toast, nfcreaderService, cleepService) {

    const nfcreaderController = function() {
        const self = this;

        self.enabled = false;
        self.backends = ["serial", "nfcpy"];
        self.backend = "serial";
        self.serialPort = "/dev/ttyUSB0";
        self.serialBaudrate = 115200;
        self.serialTimeout = 0.5;
        self.nfcpyPath = "usb";
        self.pollDelay = 0.2;
        self.dedupeSeconds = 2.0;
        self.allowedPrefixesText = "";
        self.uppercase = true;
        self.readerConnected = false;
        self.readerRunning = false;
        self.lastError = null;
        self.lastTag = null;

        self.$onInit = function() {
            cleepService.getModuleConfig("nfcreader")
                .then(function(config) {
                    self.__loadFromConfig(config);
                });
        };

        self.__loadFromConfig = function(config) {
            self.enabled = config.enabled;
            self.backend = config.backend;
            self.serialPort = config.serial_port;
            self.serialBaudrate = config.serial_baudrate;
            self.serialTimeout = config.serial_timeout;
            self.nfcpyPath = config.nfcpy_path;
            self.pollDelay = config.poll_delay;
            self.dedupeSeconds = config.dedupe_seconds;
            self.allowedPrefixesText = (config.allowed_prefixes || []).join("\n");
            self.uppercase = config.uppercase;
            self.readerConnected = config.reader_connected;
            self.readerRunning = config.reader_running;
            self.lastError = config.last_error;
            self.lastTag = config.last_tag;
        };

        self.__parsePrefixes = function() {
            return self.allowedPrefixesText
                .split(/\n|,/)
                .map(function(prefix) {
                    return prefix.trim();
                })
                .filter(Boolean);
        };

        self.save = function() {
            nfcreaderService.updateSettings({
                enabled: self.enabled,
                backend: self.backend,
                serial_port: self.serialPort,
                serial_baudrate: parseInt(self.serialBaudrate, 10),
                serial_timeout: parseFloat(self.serialTimeout),
                nfcpy_path: self.nfcpyPath,
                poll_delay: parseFloat(self.pollDelay),
                dedupe_seconds: parseFloat(self.dedupeSeconds),
                allowed_prefixes: self.__parsePrefixes(),
                uppercase: self.uppercase,
            })
                .then(function(resp) {
                    return cleepService.reloadModuleConfig("nfcreader");
                })
                .then(function(config) {
                    self.__loadFromConfig(config);
                    toast.success("Configuration saved.");
                });
        };

        self.refresh = function() {
            nfcreaderService.getStatus()
                .then(function(status) {
                    self.readerConnected = status.reader_connected;
                    self.readerRunning = status.reader_running;
                    self.lastError = status.last_error;
                    self.lastTag = status.last_tag;
                });
        };

        self.clearLastTag = function() {
            nfcreaderService.clearLastTag()
                .then(function(resp) {
                    self.lastTag = null;
                    toast.success("Last tag cleared.");
                });
        };
    };

    return {
        templateUrl: "nfcreader.config.html",
        replace: true,
        scope: true,
        controller: nfcreaderController,
        controllerAs: "$ctrl",
    };
}]);
