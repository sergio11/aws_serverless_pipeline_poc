COMPOSE_FILE = ENV.fetch("COMPOSE_FILE", "compose.yaml")
FLOCI_ENDPOINT = ENV.fetch("FLOCI_ENDPOINT", "http://localhost:4566")
FLOCI_SERVICE = ENV.fetch("FLOCI_SERVICE", "floci")
FLOCI_CONTAINER = ENV.fetch("FLOCI_CONTAINER", "poc-floci")
UI_SERVICE = ENV.fetch("UI_SERVICE", "floci-ui")
UI_CONTAINER = ENV.fetch("UI_CONTAINER", "poc-floci-ui")
BACKEND_ENDPOINT = ENV.fetch("BACKEND_ENDPOINT", "http://localhost:8000")
BACKEND_SERVICE = ENV.fetch("BACKEND_SERVICE", "backend")
BACKEND_CONTAINER = ENV.fetch("BACKEND_CONTAINER", "poc-backend")
BACKEND_DIR = ENV.fetch("BACKEND_DIR", "backend")
WORKER_SERVICE = ENV.fetch("WORKER_SERVICE", "lambda-worker")
WORKER_CONTAINER = ENV.fetch("WORKER_CONTAINER", "poc-lambda-worker")
LAMBDA_FUNCTION = ENV.fetch("LAMBDA_FUNCTION", "poc-local-document-processor")
E2E_SERVICE = ENV.fetch("E2E_SERVICE", "e2e")
INTEGRATION_SERVICE = ENV.fetch("INTEGRATION_SERVICE", "integration")
INTEGRATION_CONTAINER = ENV.fetch("INTEGRATION_CONTAINER", "poc-integration")
TERRAFORM_DIR = ENV.fetch("TERRAFORM_DIR", "terraform")
TERRAFORM_SERVICE = ENV.fetch("TERRAFORM_SERVICE", "terraform")
TERRAFORM_VOLUME = ENV.fetch("TERRAFORM_VOLUME", "terraform-workdir")
TERRAFORM_VAR_FILE = ENV.fetch("TERRAFORM_VAR_FILE", "environments/local/terraform.tfvars")

def run_command(*args)
  command = args.join(" ")
  puts command
  success = system(*args)
  abort "Command failed: #{command}" unless success
end

def ensure_terraform_volume
  existing = `podman volume inspect #{TERRAFORM_VOLUME} 2>&1`
  return if $?.success?
  run_command("podman", "volume", "create", TERRAFORM_VOLUME)
end

def sync_terraform_to_volume
  ensure_terraform_volume
  host_path = File.expand_path(TERRAFORM_DIR)
  run_command(
    "podman", "run", "--rm",
    "-v", "#{host_path}:/src:ro",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "--entrypoint", "sh",
    "aws-local-poc_terraform", "-c",
    "cp -r /src/. /terraform/"
  )
  run_command(
    "podman", "run", "--rm",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "--entrypoint", "sh",
    "aws-local-poc_terraform", "-c",
    "find /terraform/.terraform -type f -name 'terraform-provider-*' -exec chmod +x {} +; true"
  )
end

def sync_terraform_from_volume
  host_path = File.expand_path(TERRAFORM_DIR)
  run_command(
    "podman", "run", "--rm",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "-v", "#{host_path}:/host",
    "--entrypoint", "sh",
    "aws-local-poc_terraform", "-c",
    "cp -r /terraform/. /host/"
  )
end

def run_terraform(*args)
  ensure_terraform_volume
  sync_terraform_to_volume
  run_command(
    "podman", "run", "--rm",
    "--network", "poc-network",
    "-e", "AWS_ACCESS_KEY_ID=test",
    "-e", "AWS_SECRET_ACCESS_KEY=test",
    "-e", "AWS_DEFAULT_REGION=eu-west-1",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "-w", "/terraform",
    "aws-local-poc_terraform", *args
  )
  sync_terraform_from_volume
end

def terraform_output_json
  require "json"
  ensure_terraform_volume
  sync_terraform_to_volume
  output = `podman run --rm --network poc-network -e AWS_ACCESS_KEY_ID=test -e AWS_SECRET_ACCESS_KEY=test -e AWS_DEFAULT_REGION=eu-west-1 -v #{TERRAFORM_VOLUME}:/terraform -w /terraform aws-local-poc_terraform output -json`
  sync_terraform_from_volume
  abort "terraform output failed" unless $?.success?
  JSON.parse(output)
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

def wait_for_service(name, url, retries: 30, delay: 2)
  ready = false
  1.upto(retries) do |attempt|
    if system("curl", "-fsS", url, out: File::NULL, err: File::NULL)
      puts "#{name} is ready at #{url}"
      ready = true
      break
    end
    puts "Waiting for #{name} at #{url} (#{attempt}/#{retries})"
    sleep delay
  end
  abort "#{name} did not become ready at #{url}" unless ready
end

namespace :floci do
  task :up do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", FLOCI_SERVICE)
  end

  task :wait do
    wait_for_service("Floci", FLOCI_ENDPOINT)
  end

  task start: [:up, :wait]

  task :down do
    run_command("podman-compose", "-f", COMPOSE_FILE, "down")
  end
end

namespace :infra do
  task :init do
    run_terraform("init")
  end

  task :apply do
    run_terraform("apply", "-var-file=#{TERRAFORM_VAR_FILE}")
  end

  task :upload_lambda do
    run_command("bash", "scripts/package-lambda.sh")
    outputs = terraform_output_json
    bucket = outputs.dig("s3_bucket", "value")
    run_command(
      "aws", "--endpoint-url", FLOCI_ENDPOINT,
      "s3", "cp", "tmp/lambda/worker.zip",
      "s3://#{bucket}/lambda/document-processor.zip"
    )
  end

  task :env do
    outputs = terraform_output_json
    env_content = [
      "S3_BUCKET=#{outputs.dig('s3_bucket', 'value') || ''}",
      "DYNAMODB_TABLE=#{outputs.dig('dynamodb_table', 'value') || ''}",
      "SQS_QUEUE_URL=#{outputs.dig('sqs_queue_url', 'value') || ''}",
      "SQS_DLQ_URL=#{outputs.dig('sqs_dlq_url', 'value') || ''}",
    ].join("\n") + "\n"
    File.write(".env", env_content)
    puts "Generated .env from Terraform outputs"
  end

  task deploy: ["floci:start", :init, :apply, :upload_lambda, :env]

  task :destroy do
    run_terraform("destroy", "-var-file=#{TERRAFORM_VAR_FILE}")
  end
end

namespace :backend do
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", BACKEND_SERVICE)
  end

  task :start do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", BACKEND_SERVICE)
    wait_for_service("Backend", "#{BACKEND_ENDPOINT}/health")
  end

  task test: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", BACKEND_SERVICE, "pytest", "tests", "--cov=app", "--cov-report=term-missing", "--cov-fail-under=98")
  end
end

namespace :worker do
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "--profile", "worker", "build", WORKER_SERVICE)
  end

  task test: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "--profile", "worker", "run", "--rm", "--no-deps", "-T", WORKER_SERVICE, "pytest", "tests", "--cov=handler", "--cov-report=term-missing", "--cov-fail-under=98")
  end
end

namespace :integration do
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", INTEGRATION_SERVICE)
  end

  task test: ["infra:deploy", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", INTEGRATION_SERVICE, "pytest", "tests")
  end
end

namespace :e2e do
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "build", E2E_SERVICE)
  end

  task test: ["infra:deploy", "backend:start", :build] do
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", E2E_SERVICE, "pytest", "tests")
  end
end

namespace :ui do
  task :start do
    run_command("podman-compose", "-f", COMPOSE_FILE, "up", "-d", UI_SERVICE)
  end
end

namespace :test do
  task unit: ["backend:test", "worker:test"]
  task integration: "integration:test"
  task e2e: "e2e:test"
  task all: [:unit, :integration, :e2e]
end

namespace :services do
  task :logs do
    services = [FLOCI_CONTAINER, BACKEND_CONTAINER, WORKER_CONTAINER, UI_CONTAINER]
    services.each do |container|
      puts "--- #{container} ---"
      system("podman", "logs", "--tail", "50", container)
      puts
    end
  end

  task :status do
    run_command("podman", "ps", "--filter", "name=poc-", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}")
  end
end

namespace :doctor do
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

desc "Start local environment (Floci + Infra + Backend + UI)"
task up: ["infra:deploy", "backend:start", "ui:start"]

desc "Stop and destroy all services"
task down: ["infra:destroy", "floci:down"]

desc "Run all tests (unit, integration, e2e)"
task test: "test:all"

desc "Show logs for all running services"
task logs: "services:logs"

desc "Show status of all POC containers"
task status: "services:status"

desc "Check required local developer tools"
task doctor: "doctor:tools"
