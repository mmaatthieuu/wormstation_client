import queue
import threading

class USBHandler(threading.Thread):
    """USBHandler class to handle all SPI and GPIO operations in a separate thread."""

    def __init__(self, spi, gpio, logger=None):
        super().__init__()
        self.spi = spi
        self.gpio = gpio
        self.logger = logger
        self.lock = threading.Lock()  # Ensures safe USB access
        self.request_queue = queue.Queue()  # Queue to handle incoming requests
        self.response_queue = queue.Queue()  # Queue to handle responses
        self.running = True

        # Store SPI ports for different channels (0, 1, 2, etc.)
        self.spi_ports = {}

    def run(self):
        """Main loop of the USB handler thread."""
        while self.running:
            try:
                func, args, kwargs, response_queue = self.request_queue.get(block=True, timeout=1)
                if func is None:
                    break  # Exit the loop if we get a 'None' function (shutdown signal)

                with self.lock:  # Ensure thread-safe USB communication
                    result = func(*args, **kwargs)
                    if response_queue is not None:
                        response_queue.put(result)  # Send result back via the response queue
                    self.request_queue.task_done()  # Signal that task is complete
            except queue.Empty:
                continue

    def stop(self):
        """Stop the USB handler thread."""

        self.logger.log("Stopping USB handler thread.", log_level=5)

        self.running = False
        self.request_queue.put((None, None, None, None))  # Send shutdown signal
        self.join()

    def add_request(self, func, *args, **kwargs):
        """Add a new request to the queue for USB operations."""
        response_queue = kwargs.pop('response_queue', None)
        self.request_queue.put((func, args, kwargs, response_queue))

    def spi_exchange(self, data, channel, duplex=False):
        """Perform SPI exchange on a specific channel."""
        def exchange():
            spi_port = self.get_spi_port(channel)
            return spi_port.exchange(data, duplex=duplex)

        self.add_request(exchange)

    def get_spi_port(self, channel, freq=12E6, mode=0):
        """Retrieve or create an SPI port for a given channel."""
        if channel not in self.spi_ports:
            self.spi_ports[channel] = self.spi.get_port(cs=channel, freq=freq, mode=mode)
        return self.spi_ports[channel]

    def gpio_set_direction(self, pin, direction):
        """Add a request to set GPIO direction."""
        def set_direction():
            self.gpio.set_direction(pin, direction)

        self.add_request(set_direction)

    def gpio_write(self, value):
        """Add a request to write to GPIO."""
        def write():
            self.gpio.write(value)

        self.add_request(write)

    def gpio_read(self):
        """Add a request to read from GPIO."""
        response_queue = queue.Queue()  # Queue to capture the read result

        def read():
            return self.gpio.read()

        # Add the request and wait for the result
        self.add_request(read, response_queue=response_queue)
        return response_queue.get()  # Wait for the result and return it
