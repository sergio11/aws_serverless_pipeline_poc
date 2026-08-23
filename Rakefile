require "fileutils"

COMPOSE_FILE = ENV.fetch("COMPOSE_FILE", "compose.yaml")
FLOCI_ENDPOINT = ENV.fetch("FLOCI_ENDPOINT", "http://localhost:4566")
FLOCI_SERVICE = ENV.fetch("FLOCI_SERVICE", "floci")
FLOCI_CONTAINER = ENV.fetch("FLOCI_CONTAINER", "poc-floci")
UI_SERVICE = ENV.fetch("UI_SERVICE", "floci-ui")
UI_CONTAINER = ENV.fetch("UI_CONTAINER", "poc-floci-ui")
BACKEND_ENDPOINT = ENV.fetch("BACKEND_ENDPOINT", "http://localhost:8000")
BACKEND_SERVICE = ENV.fetch("BACKEND_SERVICE", "backend")
BACKEND_CONTAINER = ENV.fetch("BACKEND_CONTAINER", "poc-backend")
WORKER_SERVICE = ENV.fetch("WORKER_SERVICE", "lambda-worker")
WORKER_CONTAINER = ENV.fetch("WORKER_CONTAINER", "poc-lambda-worker")
LAMBDA_FUNCTION = ENV.fetch("LAMBDA_FUNCTION", "poc-local-document-processor")
E2E_SERVICE = ENV.fetch("E2E_SERVICE", "e2e")
INTEGRATION_SERVICE = ENV.fetch("INTEGRATION_SERVICE", "integration")
INTEGRATION_CONTAINER = ENV.fetch("INTEGRATION_CONTAINER", "poc-integration")
TERRAFORM_DIR = ENV.fetch("TERRAFORM_DIR", "terraform")
TERRAFORM_VOLUME = ENV.fetch("TERRAFORM_VOLUME", "terraform-workdir")
TERRAFORM_VAR_FILE = ENV.fetch("TERRAFORM_VAR_FILE", "environments/local/terraform.tfvars")
ROOT_PATH = File.expand_path(".")

def run_command(*args)
  command = args.join(" ")
  puts ">>> #{command}"
  success = system(*args)
  abort "FAILED: #{command}" unless success
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
    "cd /src && find . -maxdepth 1 -not -name '.terraform' -not -name 'terraform.tfstate' -not -name 'terraform.tfstate.backup' -not -name 'terraform.tfstate.*.backup' -not -name '.' -exec cp -r {} /terraform/ \\;"
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
    "cp /terraform/terraform.tfstate /terraform/terraform.tfstate.backup /terraform/.terraform.lock.hcl /host/ 2>/dev/null; true"
  )
end

def run_terraform(*args)
  ensure_terraform_volume
  sync_terraform_to_volume
  cmd = ["podman", "run", "--rm",
    "--network", "poc-network",
    "-e", "AWS_ACCESS_KEY_ID=test",
    "-e", "AWS_SECRET_ACCESS_KEY=test",
    "-e", "AWS_DEFAULT_REGION=eu-west-1",
    "-v", "#{TERRAFORM_VOLUME}:/terraform",
    "-v", "#{ROOT_PATH}:/workspace:ro",
    "-w", "/terraform",
    "aws-local-poc_terraform"] + args
  run_command(*cmd)
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
    if system("curl.exe", "-fsS", url, out: File::NULL, err: File::NULL)
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

  task :stop do
    run_command("podman-compose", "-f", COMPOSE_FILE, "stop")
  end

  task :down do
    run_command("podman-compose", "-f", COMPOSE_FILE, "down", "-t", "10")
  end

  task :clean_data do
    data_dir = File.join(ROOT_PATH, "data", "floci")
    if File.directory?(data_dir)
      puts "Cleaning Floci data directory: #{data_dir}"
      Dir.glob(File.join(data_dir, "**", "*")).each do |f|
        FileUtils.rm_rf(f)
      end
    else
      FileUtils.mkdir_p(data_dir)
    end
  end
end

namespace :infra do
  task :init do
    run_terraform("init")
  end

  task :plan do
    run_terraform("plan", "-var-file", TERRAFORM_VAR_FILE)
  end

  task :apply do
    run_terraform("apply", "-auto-approve", "-var-file", TERRAFORM_VAR_FILE)
  end

  task :package_lambda do
    vendor_dir = File.join(ROOT_PATH, "lambda", "vendor")
    output_dir = File.join(ROOT_PATH, "tmp", "lambda")
    output_zip = File.join(output_dir, "worker.zip")

    FileUtils.mkdir_p(output_dir)
    FileUtils.rm_rf(vendor_dir)
    FileUtils.rm_f(output_zip)

    run_command("python", "-m", "pip", "install", "-q", "-t", vendor_dir, "-r",
                File.join(ROOT_PATH, "lambda", "requirements.txt"))

    lambda_dir = File.join(ROOT_PATH, "lambda")
    Dir.chdir(lambda_dir) do
      run_command("python", "-c",
        "import zipfile, pathlib; " \
        "z = zipfile.ZipFile('../tmp/lambda/worker.zip', 'w', zipfile.ZIP_DEFLATED); " \
        "z.write('handler.py', 'handler.py'); " \
        "[z.write(str(p), str(p)) for p in pathlib.Path('vendor').rglob('*') if p.is_file()]; " \
        "z.close()"
      )
    end

    FileUtils.rm_rf(vendor_dir)
    size = File.size(output_zip)
    puts "Lambda package created: #{output_zip} (#{size} bytes)"
  end

  task :upload_lambda do
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
    queue_url = outputs.dig('sqs_queue_url', 'value') || ''
    queue_name = queue_url.split('/').last || ''
    env_content = [
      "S3_BUCKET=#{outputs.dig('s3_bucket', 'value') || ''}",
      "DYNAMODB_TABLE=#{outputs.dig('dynamodb_table', 'value') || ''}",
      "SQS_QUEUE_URL=#{queue_url}",
      "SQS_QUEUE_NAME=#{queue_name}",
      "SQS_DLQ_URL=#{outputs.dig('sqs_dlq_url', 'value') || ''}",
    ].join("\n") + "\n"
    File.write(".env", env_content)
    puts "Generated .env from Terraform outputs"
  end

  task deploy: ["floci:start", :package_lambda, :init, :apply, :env]

  task :destroy do
    run_terraform("destroy", "-auto-approve", "-lock=false", "-var-file", TERRAFORM_VAR_FILE)
  end

  task :clean_floci do
    outputs = terraform_output_json
    bucket = outputs.dig("s3_bucket", "value")
    puts "Cleaning S3 bucket: #{bucket}"
    list_cmd = "podman run --rm --network poc-network --entrypoint sh aws-local-poc_terraform -c " \
      "\"curl -s 'http://floci:4566/#{bucket}/?list-type=2' | grep -o '<Key>[^<]*</Key>' | sed 's/<[^>]*>//g'\""
    keys = `#{list_cmd}`.strip.split("\n").reject(&:empty?)
    keys.each do |key|
      run_command("podman", "run", "--rm", "--network", "poc-network", "--entrypoint", "sh",
        "aws-local-poc_terraform", "-c",
        "curl -s -X DELETE 'http://floci:4566/#{bucket}/#{key}'")
    end
    puts "Cleaned #{keys.length} objects from bucket"
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
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", BACKEND_SERVICE,
                "pytest", "tests", "--cov=app", "--cov-report=term-missing", "--cov-fail-under=98")
  end
end

namespace :worker do
  task :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "--profile", "worker", "build", WORKER_SERVICE)
  end

  task test: :build do
    run_command("podman-compose", "-f", COMPOSE_FILE, "--profile", "worker", "run", "--rm", "--no-deps", "-T", WORKER_SERVICE,
                "pytest", "tests", "--cov=handler", "--cov-report=term-missing", "--cov-fail-under=98")
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
    run_command("podman-compose", "-f", COMPOSE_FILE, "run", "--rm", "--no-deps", "-T", E2E_SERVICE, "pytest", "tests", "-v")
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
  task all: [:unit, :e2e]
end

namespace :services do
  task :logs do
    [FLOCI_CONTAINER, BACKEND_CONTAINER, WORKER_CONTAINER, UI_CONTAINER].each do |container|
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
      "curl.exe" => "HTTP readiness checks",
      "python" => "Lambda packaging"
    }.each do |command, purpose|
      status = command_available?(command) ? "OK" : "MISSING"
      puts "#{command.ljust(15)} #{status.ljust(8)} #{purpose}"
    end
  end
end

desc "Start local environment (Floci + Infra + Backend + UI)"
task up: ["infra:deploy", "backend:start", "ui:start"]

desc "Stop and destroy all services"
task down: ["floci:stop", "floci:clean_data", "floci:start", "infra:destroy", "floci:stop"]

desc "Run all tests (unit, e2e)"
task test: "test:all"

desc "Show logs for all running services"
task logs: "services:logs"

desc "Show status of all POC containers"
task status: "services:status"

desc "Check required local developer tools"
task doctor: "doctor:tools"
