defmodule Risteys.Repo.Migrations.CreateCoxHrs do
  use Ecto.Migration

  def change do
    create table(:cox_hrs) do
      add :hr, :float, null: false
      add :ci_min, :float, null: false
      add :ci_max, :float, null: false
      add :pvalue, :float, null: false
      add :n_individuals, :integer, null: false
      add :prior_id, references(:phenocodes, on_delete: :delete_all), null: false
      add :outcome_id, references(:phenocodes, on_delete: :delete_all), null: false

      timestamps()
    end

    create unique_index(:cox_hrs, [:prior_id, :outcome_id], name: :prior_outcome)
  end
end
