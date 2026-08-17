COMPOSE_FILE = ENV.fetch("COMPOSE_FILE", "compose.yaml")
FLOCI_ENDPOINT = ENV.fetch("FLOCI_ENDPOINT", "http://localhost:4566")
FLOCI_SERVICE = ENV.fetch("FLOCI_SERVICE", "floci")
FLOCI_CONTAINER = ENV.fetch("FLOCI_CONTAINER", "poc-floci")

def run_command(*args)
  command = args.join(" ")
  puts command
  success = system(*args)
  abort "Command failed: #{command}" unless success
end

namespace :floci do
  desc "Validate the Podman Compose configuration"
  task :config do
    run_command("podman-compose", "-f", COMPOSE_FILE, "config")
  end

  desc "Start the Floci local AWS emulator"
  task :up do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", FLOCI_SERVICE)
  end

  desc "Wait until Floci responds on FLOCI_ENDPOINT"
  task :wait do
    retries = ENV.fetch("FLOCI_WAIT_RETRIES", "30").to_i
    delay = ENV.fetch("FLOCI_WAIT_DELAY_SECONDS", "2").to_i
    ready = false

    1.upto(retries) do |attempt|
      if system("curl", "-fsS", FLOCI_ENDPOINT, out: File::NULL, err: File::NULL)
        puts "Floci is ready at #{FLOCI_ENDPOINT}"
        ready = true
        break
      end

      puts "Waiting for Floci at #{FLOCI_ENDPOINT} (#{attempt}/#{retries})"
      sleep delay
    end

    abort "Floci did not become ready at #{FLOCI_ENDPOINT}" unless ready
  end

  desc "Start Floci and wait until it is ready"
  task start: [:up, :wait]

  desc "Show Floci container status"
  task :status do
    run_command("podman", "ps", "--filter", "name=#{FLOCI_CONTAINER}", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show Floci logs"
  task :logs do
    run_command("podman", "logs", FLOCI_CONTAINER)
  end

  desc "Stop the local Compose environment"
  task :down do
    run_command("podman-compose", "-f", COMPOSE_FILE, "down")
  end
end

desc "Start the local AWS emulator"
task up: "floci:start"

desc "Stop the local AWS emulator"
task down: "floci:down"
