COMPOSE_FILE = ENV.fetch("COMPOSE_FILE", "compose.yaml")
FLOCI_ENDPOINT = ENV.fetch("FLOCI_ENDPOINT", "http://localhost:4566")
FLOCI_SERVICE = ENV.fetch("FLOCI_SERVICE", "floci")
FLOCI_CONTAINER = ENV.fetch("FLOCI_CONTAINER", "poc-floci")
BACKEND_ENDPOINT = ENV.fetch("BACKEND_ENDPOINT", "http://localhost:8000")
BACKEND_SERVICE = ENV.fetch("BACKEND_SERVICE", "backend")
BACKEND_CONTAINER = ENV.fetch("BACKEND_CONTAINER", "poc-backend")
BACKEND_DIR = ENV.fetch("BACKEND_DIR", "backend")
WORKER_SERVICE = ENV.fetch("WORKER_SERVICE", "lambda-worker")
WORKER_CONTAINER = ENV.fetch("WORKER_CONTAINER", "poc-lambda-worker")
E2E_SERVICE = ENV.fetch("E2E_SERVICE", "e2e")
TERRAFORM_DIR = ENV.fetch("TERRAFORM_DIR", "terraform")
TERRAFORM_VAR_FILE = ENV.fetch("TERRAFORM_VAR_FILE", "environments/local/terraform.tfvars")

def run_command(*args)
  command = args.join(" ")
  puts command
  success = system(*args)
  abort "Command failed: #{command}" unless success
end

def command_available?(command)
  extensions = ENV.fetch("PATHEXT", "").split(";")
  extensions = [""] if extensions.empty?

  ENV.fetch("PATH", "").split(File::PATH_SEPARATOR).any? do |path|
    extensions.any? do |extension|
      File.executable?(File.join(path, "#{command}#{extension}"))
    end
  end
end

namespace :doctor do
  desc "Check required local developer tools"
  task :tools do
    {
      "ruby" => "Ruby runtime for Rake tasks",
      "rake" => "Task runner",
      "podman" => "Container runtime",
      "podman-compose" => "Compose runner for Podman",
      "curl" => "HTTP readiness checks",
      "terraform" => "Infrastructure provisioning",
      "aws" => "AWS CLI diagnostics"
    }.each do |command, purpose|
      status = command_available?(command) ? "OK" : "MISSING"
      puts "#{command.ljust(15)} #{status.ljust(8)} #{purpose}"
    end
  end
end

namespace :compose do
  desc "Validate the Compose file"
  task :config do
    run_command("podman-compose", "-f", COMPOSE_FILE, "config")
  end

  desc "Build all local images"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build")
  end

  desc "Show running POC containers"
  task :status do
    run_command("podman", "ps", "--filter", "name=poc-", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show Compose logs"
  task :logs do
    run_command("podman-compose", "-f", COMPOSE_FILE, "logs")
  end
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

namespace :infra do
  desc "Initialize Terraform"
  task :init do
    run_command("terraform", "-chdir=#{TERRAFORM_DIR}", "init")
  end

  desc "Format Terraform files"
  task :fmt do
    run_command("terraform", "-chdir=#{TERRAFORM_DIR}", "fmt", "-recursive")
  end

  desc "Validate Terraform configuration"
  task validate: :init do
    run_command("terraform", "-chdir=#{TERRAFORM_DIR}", "validate")
  end

  desc "Show Terraform plan for local infrastructure"
  task plan: ["floci:start", :init] do
    run_command("terraform", "-chdir=#{TERRAFORM_DIR}", "plan", "-var-file=#{TERRAFORM_VAR_FILE}")
  end

  desc "Apply Terraform local infrastructure"
  task apply: ["floci:start", :init] do
    run_command("terraform", "-chdir=#{TERRAFORM_DIR}", "apply", "-var-file=#{TERRAFORM_VAR_FILE}")
  end

  desc "Destroy Terraform local infrastructure"
  task destroy: ["floci:start", :init] do
    run_command("terraform", "-chdir=#{TERRAFORM_DIR}", "destroy", "-var-file=#{TERRAFORM_VAR_FILE}")
  end

  desc "Show Terraform outputs"
  task :output do
    run_command("terraform", "-chdir=#{TERRAFORM_DIR}", "output")
  end
end

namespace :backend do
  desc "Build the backend container"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", BACKEND_SERVICE)
  end

  desc "Run backend tests"
  task test: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", BACKEND_SERVICE, "pytest", "tests")
  end

  desc "Start the backend service"
  task up: "floci:start" do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", BACKEND_SERVICE)
  end

  desc "Wait until the backend health endpoint responds"
  task :wait do
    endpoint = "#{BACKEND_ENDPOINT}/health"
    retries = ENV.fetch("BACKEND_WAIT_RETRIES", "30").to_i
    delay = ENV.fetch("BACKEND_WAIT_DELAY_SECONDS", "2").to_i
    ready = false

    1.upto(retries) do |attempt|
      if system("curl", "-fsS", endpoint, out: File::NULL, err: File::NULL)
        puts "Backend is ready at #{endpoint}"
        ready = true
        break
      end

      puts "Waiting for backend at #{endpoint} (#{attempt}/#{retries})"
      sleep delay
    end

    abort "Backend did not become ready at #{endpoint}" unless ready
  end

  desc "Start backend and wait until it is ready"
  task start: [:up, :wait]

  desc "Show backend container status"
  task :status do
    run_command("podman", "ps", "--filter", "name=#{BACKEND_CONTAINER}", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show backend logs"
  task :logs do
    run_command("podman", "logs", BACKEND_CONTAINER)
  end

  desc "Run backend HTTP smoke check"
  task smoke: :start do
    run_command("curl", "-fsS", "#{BACKEND_ENDPOINT}/health")
  end
end

namespace :worker do
  desc "Build the Lambda-style worker container"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", WORKER_SERVICE)
  end

  desc "Run worker tests"
  task test: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", WORKER_SERVICE, "pytest", "tests")
  end

  desc "Process one SQS receive cycle and exit"
  task run_once: ["floci:start", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "-T", WORKER_SERVICE, "python", "handler.py", "--once")
  end

  desc "Start the polling worker"
  task start: ["floci:start", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", WORKER_SERVICE)
  end

  desc "Show worker container status"
  task :status do
    run_command("podman", "ps", "--filter", "name=#{WORKER_CONTAINER}", "--format", "{{.Names}} {{.Status}} {{.Ports}}")
  end

  desc "Show worker logs"
  task :logs do
    run_command("podman", "logs", WORKER_CONTAINER)
  end
end

namespace :e2e do
  desc "Build the end-to-end test container"
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", E2E_SERVICE)
  end

  desc "Run end-to-end document workflow tests"
  task test: ["backend:start", "worker:start", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", E2E_SERVICE, "pytest", "tests")
  end
end

namespace :test do
  desc "Run unit/API tests for backend and worker"
  task unit: ["backend:test", "worker:test"]

  desc "Run end-to-end tests"
  task e2e: "e2e:test"

  desc "Run all tests"
  task all: [:unit, :e2e]
end

namespace :verify do
  desc "Run hardening verification"
  task hardening: ["doctor:tools", "ci", "compose:status"]
end

namespace :acceptance do
  desc "Run final POC acceptance checks"
  task :check do
    Rake::Task["doctor:tools"].invoke
    Rake::Task["ci"].invoke
    puts "Acceptance checks completed. Review docs/acceptance-report.md for remaining tooling gaps."
  end
end

desc "Start the local AWS emulator"
task up: "floci:start"

desc "Stop the local AWS emulator"
task down: "floci:down"

desc "Provision local AWS-compatible infrastructure"
task infra: "infra:apply"

desc "Run all tests"
task test: "test:all"

desc "Check required local developer tools"
task doctor: "doctor:tools"

desc "Build all local images"
task build: "compose:build"

desc "Show running POC containers"
task status: "compose:status"

desc "Run CI validation locally"
task ci: ["compose:config", "test:all"]

desc "Run hardening verification"
task verify: "verify:hardening"

desc "Run final POC acceptance checks"
task acceptance: "acceptance:check"
